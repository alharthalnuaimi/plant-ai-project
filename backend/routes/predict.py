from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from schemas.contracts import OrchestratorRequest, OrchestratorResponse, SurvivalSensorInput, VisionResult
from services.config_loader import get_runtime_config
from services.orchestrator import run_analysis_pipeline
from services import analytics_store
from services.plant_health import enrich_vision_result
from services.prediction import run_vision_prediction

router = APIRouter(tags=["predict"])

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


@router.post("/predict", response_model=VisionResult)
async def predict(
    file: UploadFile = File(...),
    user_id: str = Form(default="demo_user"),
    zone_id: str = Form(default="zone_alpha"),
) -> VisionResult:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Expected an image upload")
    data = await file.read()
    if len(data) < _min_image_bytes():
        raise HTTPException(status_code=400, detail="Image too small or empty")

    uid = _normalize_user_id(user_id)
    zid = _normalize_zone_id(zone_id)

    # Optional: persist for demo/debug
    fname = f"{uuid.uuid4().hex}_{file.filename or 'image'}"
    dest = UPLOAD_DIR / fname
    dest.write_bytes(data)

    # Run inference. If a real model is configured but throws (e.g. corrupt
    # weights at runtime), translate that into a 503 so the UI can show a
    # clean "Vision engine unavailable" banner instead of a 500 stacktrace.
    try:
        pred = run_vision_prediction(data)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail=f"Vision engine failed: {type(exc).__name__}",
        ) from exc

    meta = dict(pred.metadata)
    meta["saved_path"] = str(dest.relative_to(UPLOAD_DIR.parent))
    meta["user_id"] = uid
    meta["zone_id"] = zid
    base = pred.model_copy(update={"user_id": uid, "zone_id": zid, "metadata": meta})
    result = enrich_vision_result(base, uid, zid, "esp32_001")
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
