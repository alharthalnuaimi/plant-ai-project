from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from schemas.contracts import OrchestratorRequest, OrchestratorResponse, SurvivalSensorInput, VisionResult
from services.config_loader import get_runtime_config
from services.orchestrator import run_analysis_pipeline
from services import analytics_store, sensor_store, storage
from services.plant_health import enrich_vision_result
from services.prediction import run_vision_prediction

router = APIRouter(tags=["predict"])

log = logging.getLogger("plantvision.predict")

UPLOAD_DIR = Path(__file__).resolve().parent.parent / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _min_image_bytes() -> int:
    return int(
        get_runtime_config()
        .get("thresholds", {})
        .get("prediction", {})
        .get("min_image_bytes", 32)
    )


def _normalize_user_id(user_id: str | None) -> str:
    uid = (user_id or "demo_user").strip()
    return uid or "demo_user"


def _normalize_zone_id(zone_id: str | None) -> str:
    zid = (zone_id or "zone_alpha").strip()
    return zid or "zone_alpha"


def _normalize_device_id(device_id: str | None) -> str:
    did = (device_id or "esp32_001").strip()
    return did or "esp32_001"


@router.post("/predict", response_model=VisionResult)
async def predict(
    file: UploadFile = File(...),
    user_id: str = Form(default="demo_user"),
    zone_id: str = Form(default="zone_alpha"),
    device_id: str = Form(default="esp32_001"),
    source: str = Form(default="upload"),
    plant_id: str = Form(default=""),
    plant_name: str = Form(default=""),
    # Phase 3 — plant identification controls (additive, all optional)
    species_id: str = Form(
        default="",
        description="Optional manual species lock (e.g. 'cucumber'). Skips the identifier model.",
    ),
    identify: bool = Form(
        default=True,
        description="Run plant identification (default true). Disable for fastest path on known plants.",
    ),
) -> VisionResult:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Expected an image upload")
    data = await file.read()
    if len(data) < _min_image_bytes():
        raise HTTPException(status_code=400, detail="Image too small or empty")

    uid = _normalize_user_id(user_id)
    zid = _normalize_zone_id(zone_id)
    did = _normalize_device_id(device_id)
    src = (source or "upload").strip().lower() or "upload"

    # Phase 4 — try Supabase Storage first; gracefully fall back to the
    # legacy `backend/uploads/` write path when Storage is disabled OR
    # the upload errors out. The downstream persistence layer just reads
    # `meta["saved_path"]` so both branches are wire-compatible.
    storage_used = False
    fallback = True
    image_storage_path: str
    image_public_url: str | None = None

    if storage.is_enabled():
        upload_res = await storage.upload_scan_image(
            file_bytes=data,
            filename=file.filename or "image",
            content_type=file.content_type or "image/jpeg",
        )
        if upload_res.ok and upload_res.object_path:
            storage_used = True
            fallback = False
            image_storage_path = upload_res.object_path
            image_public_url = upload_res.public_url
        else:
            log.warning(
                "predict storage upload failed; using local fallback (error=%s)",
                upload_res.error,
            )

    if not storage_used:
        fname = f"{uuid.uuid4().hex}_{file.filename or 'image'}"
        dest = UPLOAD_DIR / fname
        dest.write_bytes(data)
        image_storage_path = dest.relative_to(UPLOAD_DIR.parent).as_posix()

    log.info(
        "predict image persisted storage_used=%s fallback=%s path=%s",
        storage_used,
        fallback,
        image_storage_path,
    )

    # Run inference. If a real model is configured but throws (e.g. corrupt
    # weights at runtime), translate that into a 503 so the UI can show a
    # clean "Vision engine unavailable" banner instead of a 500 stacktrace.
    try:
        pred = run_vision_prediction(
            data,
            identify=bool(identify),
            species_id=(species_id or None),
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Vision engine failed: {type(exc).__name__}",
        ) from exc

    meta = dict(pred.metadata)
    meta["saved_path"] = image_storage_path
    if image_public_url:
        # Surface the Supabase public URL in two places so existing
        # consumers (frontend `image_url`, scan-history surface) keep
        # working without any frontend changes.
        meta["image_url"] = image_public_url
        meta["image_public_url"] = image_public_url
    else:
        meta["image_url"] = "/" + image_storage_path  # served by /uploads static mount
    meta["user_id"] = uid
    meta["zone_id"] = zid
    meta["device_id"] = did
    meta["scan_source"] = src

    # Optional plant identity (Phase 3 placeholder — future plant_profiles table)
    pid = (plant_id or "").strip()
    pname = (plant_name or "").strip()
    if pid:
        meta["plant_id"] = pid
    if pname:
        meta["plant_name"] = pname

    # Mirror plant identification into metadata so persisted scans (and the
    # Plant Profile aggregate route) can read identity without re-running
    # the model. Backwards-compatible: legacy rows simply won't have these.
    if pred.plant is not None:
        meta["plant_identification"] = {
            "species_id": pred.plant.species_id,
            "common_name": pred.plant.common_name,
            "scientific_name": pred.plant.scientific_name,
            "family": pred.plant.family,
            "genus": pred.plant.genus,
            "confidence": pred.plant.confidence,
            "source": pred.plant.source,
        }
        # Convenience: when no manual plant_name was supplied, default the
        # display name to the identified common_name. Keeps the analytics
        # / scan-history grids visually consistent.
        if not pname and pred.plant.common_name:
            meta.setdefault("plant_name", pred.plant.common_name)

    # Snapshot the latest sensor reading for this user/zone/device so the
    # scan detail view can show env conditions even after backend restart.
    snap = sensor_store.get_latest(user_id=uid, zone_id=zid, device_id=did)
    if snap is not None:
        meta["sensor_snapshot"] = {
            "air_temperature": snap.air_temperature,
            "air_humidity":    snap.air_humidity,
            "light_lux":       snap.light_lux,
            "soil_temperature": snap.soil_temperature,
            "soil_humidity":   snap.soil_humidity,
            "soil_ph":         snap.soil_ph,
            "soil_ec":         snap.soil_ec,
            "timestamp":       snap.timestamp,
        }

    base = pred.model_copy(update={"user_id": uid, "zone_id": zid, "metadata": meta})
    result = enrich_vision_result(base, uid, zid, did)

    # Phase 3: Gemini Second-Opinion & Disagreement Logging
    try:
        from services.gemini_second_opinion import evaluate_gemini_second_opinion
        g_verdict, g_agrees, g_reasoning = evaluate_gemini_second_opinion(
            image_bytes=data,
            yolo_label=result.disease,
            yolo_confidence=result.confidence,
            image_ref=image_storage_path,
        )
        result = result.model_copy(update={
            "gemini_verdict": g_verdict,
            "gemini_agrees": g_agrees,
            "gemini_reasoning": g_reasoning,
        })
    except Exception as exc:
        log.warning("Gemini second opinion non-fatal error: %s", exc)

    analytics_store.record_scan(result)
    return result


@router.post("/analyze", response_model=OrchestratorResponse)
async def analyze(
    request: Request,
    file: UploadFile = File(...),
    soil_moisture: float = Form(...),
    temperature: float = Form(...),
    humidity: float = Form(...),
    species: str | None = Form(default=None),
    user_question: str | None = Form(default=None),
) -> OrchestratorResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Expected an image upload")
    image_bytes = await file.read()
    if len(image_bytes) < _min_image_bytes():
        raise HTTPException(status_code=400, detail="Image too small or empty")

    payload = OrchestratorRequest(
        sensors=SurvivalSensorInput(
            soil_moisture=soil_moisture,
            temperature=temperature,
            humidity=humidity,
            species=species,
        ),
        user_question=user_question,
        persist_upload=True,
    )
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return run_analysis_pipeline(
        request_id=request_id,
        image_bytes=image_bytes,
        request=payload,
    )
