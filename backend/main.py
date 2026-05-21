"""
Plant health MVP API: vision → structured signals → rule-based survival → Llama narrative.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from config.settings import SETTINGS
from core.errors import AppError
from core.observability import wire_observability
from db.connection import close_pool, get_pool, ping
from routes.analytics import router as analytics_router
from routes.chat import router as chat_router
from routes.dataset_meta import router as dataset_meta_router
from routes.devices import router as devices_router
from routes.health_route import router as health_router
from routes.predict import router as predict_router
from routes.sensor import router as sensor_router
from routes.survival import router as survival_router
from routes.zones import router as zones_router

app = FastAPI(
    title="Plant Health MVP",
    description="Vision classifies images; Llama only reasons over structured context.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.on_event("startup")
async def _startup() -> None:
    if SETTINGS.use_postgres:
        await get_pool()


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


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "uptime_sec": int(time.time() - _APP_STARTED_AT),
    }


@app.get("/health/db")
async def health_db() -> dict:
    """Reports persistence backend state (Postgres reachable or memory fallback)."""

    ok = await ping() if SETTINGS.use_postgres else False
    return {
        "persistence_backend": SETTINGS.persistence_backend,
        "postgres_reachable": ok,
        "database_host": SETTINGS.postgres_host,
        "database_port": SETTINGS.postgres_port,
        "database_name": SETTINGS.postgres_db,
    }
