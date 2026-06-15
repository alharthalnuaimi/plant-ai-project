"""
Plant health MVP API: vision → structured signals → rule-based survival → Llama narrative.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

import asyncio
import logging

from config.settings import SETTINGS
from core.cors import resolved_cors_origins
from core.errors import AppError
from core.observability import wire_observability
from core.retry import record_validation_failure
from db.connection import close_pool, deployment_mode, get_pool, ping
from repositories import analytics_events_repo
from services import analytics_store, audit_log
from routes.analytics import router as analytics_router
from routes.care import router as care_router
from routes.chat import router as chat_router
from routes.dataset_meta import router as dataset_meta_router
from routes.devices import router as devices_router
from routes.health_route import router as health_router
from routes.predict import router as predict_router
from routes.report import router as report_router
from routes.scans import router as scans_router
from routes.sensor import router as sensor_router
from routes.survival import router as survival_router
from routes.zones import router as zones_router

app = FastAPI(
    title="Plant Health MVP",
    description="Vision classifies images; Llama only reasons over structured context.",
    version="0.1.0",
)

# Phase 4 — CORS allowlist is now env-driven.
#   CORS_ALLOWED_ORIGINS unset / empty / "*"  -> ["*"] (legacy behaviour)
#   CORS_ALLOWED_ORIGINS="https://a,https://b" -> ["https://a", "https://b"]
# See ``core.cors`` for the parser + DEPLOY.md §3.1 for the deploy guide.
_CORS_ORIGINS = resolved_cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
wire_observability(app)

_APP_STARTED_AT = time.time()

app.include_router(analytics_router)
app.include_router(predict_router)
app.include_router(sensor_router)
app.include_router(survival_router)
app.include_router(chat_router)
app.include_router(dataset_meta_router)
app.include_router(health_router)
app.include_router(zones_router)
app.include_router(devices_router)
app.include_router(scans_router)
app.include_router(care_router)
app.include_router(report_router)

# Static mount so the frontend can render scan thumbnails saved by /predict.
# Images live under backend/uploads/ and are referenced as /uploads/<name>
# in scan_results.metadata_json.image_url.
from pathlib import Path
from fastapi.staticfiles import StaticFiles
_UPLOADS_DIR = Path(__file__).resolve().parent / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")


_LOG = logging.getLogger("plantvision.startup")


@app.on_event("startup")
async def _startup() -> None:
    if SETTINGS.use_postgres:
        await get_pool()
        # Hydrate in-memory analytics from the DB so /analytics/history,
        # /analytics/summary, the Home scan log and the AI assistant context
        # all survive a backend restart.
        try:
            loaded = await analytics_store.hydrate_from_db()
            if loaded:
                _LOG.info("Hydrated %d scan(s) from scan_results into in-memory analytics", loaded)
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("Scan history hydration skipped: %s", exc)


@app.on_event("shutdown")
async def _shutdown() -> None:
    await close_pool()


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "n/a")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": str(exc.detail), "request_id": request_id},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "n/a")
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "request_id": request_id},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "n/a")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.code, "message": exc.message, "request_id": request_id},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Phase 3 — log validation failures on /sensor as analytics_events.

    Without this handler, FastAPI returns a 422 but no breadcrumb of *why*
    is persisted — making it impossible to diagnose ESP32 firmware bugs
    after the fact. We persist a structured event for /sensor specifically
    (the highest-traffic write path) and let other routes fall through to
    the standard 422 response shape.
    """

    request_id = getattr(request.state, "request_id", "n/a")
    path = request.url.path

    if path == "/sensor":
        record_validation_failure(path)
        # Phase 3 — also persist a structured audit row for ops visibility.
        try:
            err_summary = []
            for e in exc.errors()[:10]:
                err_summary.append({
                    "loc": ".".join(str(p) for p in e.get("loc", [])),
                    "msg": str(e.get("msg", "")),
                    "type": str(e.get("type", "")),
                })
            audit_log.log_validation_event(
                route=path,
                request_id=request_id,
                actor=request.client.host if request.client else None,
                payload={"errors": err_summary},
            )
        except Exception:  # noqa: BLE001
            pass

    if path == "/sensor" and SETTINGS.use_postgres and SETTINGS.persist_events:
        # Best-effort, non-blocking: never let an audit write delay the 422.
        async def _log_invalid_sensor() -> None:
            try:
                # `errors()` items contain non-serialisable objects in pydantic v2;
                # reduce to a plain str → list[str] mapping.
                err_list = []
                for e in exc.errors()[:10]:
                    err_list.append({
                        "loc": ".".join(str(p) for p in e.get("loc", [])),
                        "msg": str(e.get("msg", "")),
                        "type": str(e.get("type", "")),
                    })
                await analytics_events_repo.insert_event(
                    event_type="sensor_validation_failed",
                    category="sensor",
                    title="Invalid sensor payload",
                    message=f"/sensor rejected payload (request_id={request_id})",
                    payload={
                        "request_id": request_id,
                        "errors": err_list,
                        "client": request.client.host if request.client else None,
                    },
                )
            except Exception as log_exc:  # noqa: BLE001
                logging.getLogger("plantvision.sensor.validate").warning(
                    "could not persist sensor validation event: %s", log_exc
                )

        try:
            asyncio.get_running_loop().create_task(_log_invalid_sensor())
        except RuntimeError:
            pass

    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "request_id": request_id,
            "details": exc.errors(),
        },
    )


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "uptime_sec": int(time.time() - _APP_STARTED_AT),
    }


@app.get("/health/db")
async def health_db() -> dict:
    """Persistence backend status — Supabase Cloud, local Postgres, or memory."""

    from urllib.parse import urlparse

    mode = deployment_mode()  # "cloud" | "local" | "memory"
    ok = await ping() if SETTINGS.use_postgres else False
    parsed = urlparse(SETTINGS.database_url) if SETTINGS.use_postgres else None
    host = (parsed.hostname if parsed else None) or SETTINGS.postgres_host
    port = (parsed.port if parsed else None) or SETTINGS.postgres_port

    if not SETTINGS.use_postgres:
        status = "memory_fallback"
    elif ok and mode == "cloud":
        status = "supabase_cloud_connected"
    elif ok:
        status = "postgres_connected"
    else:
        status = "postgres_unreachable"

    return {
        "persistence_backend": SETTINGS.persistence_backend,
        "deployment": mode,
        "status": status,
        "postgres_reachable": ok,
        "database_host": host,
        "database_port": port,
        "database_name": SETTINGS.postgres_db,
    }
