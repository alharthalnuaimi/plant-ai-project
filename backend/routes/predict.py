from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from core.errors import AppError
from schemas.contracts import OrchestratorRequest, OrchestratorResponse, SurvivalSensorInput, VisionResult
from services.config_loader import get_runtime_config
from services.feedback_store import FEEDBACK_STORE
from services.gemini.config import load_gemini_config
from services.gemini.errors import ImageTooLargeError
from services.orchestrator import run_analysis_pipeline
from services import analytics_store, sensor_store, storage
from services.plant_health import enrich_vision_result
from services.preprocess import decoded_image_type
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


async def _read_image(file: UploadFile) -> tuple[bytes, str, str]:
    """Read and validate an upload: image content type, size limits, decodable."""

    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Expected an image upload")
    max_bytes = load_gemini_config().max_upload_bytes
    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ImageTooLargeError(max_bytes)
    if len(data) < _min_image_bytes():
        raise HTTPException(status_code=400, detail="Image too small or empty")
    try:
        image_ext, image_type = decoded_image_type(data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Uploaded file is not a readable image") from exc
    return data, image_ext, image_type


async def _diagnose(data: bytes, *, identify: bool, species_id: str | None) -> VisionResult:
    """Gemini diagnosis off the event loop; structured errors pass through unchanged."""

    try:
        return await run_in_threadpool(
            run_vision_prediction, data, identify=identify, species_id=species_id
        )
    except (HTTPException, AppError):
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("diagnosis failed unexpectedly")
        raise HTTPException(
            status_code=503,
            detail=f"Diagnosis failed: {type(exc).__name__}",
        ) from exc


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
        max_length=100,
        description="Optional manual species lock (e.g. 'cucumber'). Sent to Gemini as a hint and echoed back as the plant identity.",
    ),
    identify: bool = Form(
        default=True,
        description="Run plant identification (default true). Disable for fastest path on known plants.",
    ),
) -> VisionResult:
    data, image_ext, image_type = await _read_image(file)

    uid = _normalize_user_id(user_id)
    zid = _normalize_zone_id(zone_id)
    did = _normalize_device_id(device_id)
    src = (source or "upload").strip().lower() or "upload"

    # Diagnose first: if Gemini fails, nothing is persisted and the client
    # gets a structured, retryable error (no fabricated fallback result).
    pred = await _diagnose(data, identify=bool(identify), species_id=(species_id or None))

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
            filename=f"scan.{image_ext}",
            content_type=image_type,
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
        fname = f"{uuid.uuid4().hex}.{image_ext}"  # the client's filename is never trusted
        dest = UPLOAD_DIR / fname
        dest.write_bytes(data)
        image_storage_path = dest.relative_to(UPLOAD_DIR.parent).as_posix()

    log.info(
        "predict image persisted storage_used=%s fallback=%s path=%s",
        storage_used,
        fallback,
        image_storage_path,
    )

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

    # Queue low-confidence / non-assessable diagnoses for human review
    # (admin feedback queue). The legacy ``yolo_*`` field names hold the
    # primary diagnosis, which now comes from Gemini.
    if not result.accepted or result.confidence < 0.60:
        try:
            label = (result.metadata or {}).get("raw_disease_label") or result.disease
            FEEDBACK_STORE.insert_feedback(
                image_ref=image_storage_path,
                yolo_label=label,
                yolo_confidence=result.confidence,
                gemini_label=label,
                gemini_agrees=True,
                reasoning=f"Low-confidence Gemini diagnosis. {result.gemini_reasoning or ''}".strip(),
            )
        except Exception as exc:  # noqa: BLE001 - review queue is best-effort
            log.warning("feedback queue insert failed: %s", exc)

    analytics_store.record_scan(result)
    return result


@router.post("/analyze", response_model=OrchestratorResponse)
async def analyze(
    request: Request,
    file: UploadFile = File(...),
    soil_moisture: float = Form(...),
    temperature: float = Form(...),
    humidity: float = Form(...),
    species: str | None = Form(default=None, max_length=100),
    user_question: str | None = Form(default=None, max_length=2000),
) -> OrchestratorResponse:
    image_bytes, _, _ = await _read_image(file)

    try:
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
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return await run_in_threadpool(
        run_analysis_pipeline,
        request_id=request_id,
        image_bytes=image_bytes,
        request=payload,
    )
