from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from schemas.contracts import OrchestratorRequest, OrchestratorResponse, SurvivalSensorInput, VisionResult
from services.config_loader import get_runtime_config
from services.orchestrator import run_analysis_pipeline
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


@router.post("/predict", response_model=VisionResult)
async def predict(file: UploadFile = File(...)) -> VisionResult:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Expected an image upload")
    data = await file.read()
    if len(data) < _min_image_bytes():
        raise HTTPException(status_code=400, detail="Image too small or empty")

    # Optional: persist for demo/debug
    fname = f"{uuid.uuid4().hex}_{file.filename or 'image'}"
    dest = UPLOAD_DIR / fname
    dest.write_bytes(data)

    pred = run_vision_prediction(data)
    meta = dict(pred.metadata)
    meta["saved_path"] = str(dest.relative_to(UPLOAD_DIR.parent))
    return pred.model_copy(update={"metadata": meta})


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
