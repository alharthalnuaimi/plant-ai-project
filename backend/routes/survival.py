from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from schemas.contracts import SensorInput, SurvivalResponse, VisionResult
from services.survival import SurvivalInputs, compute_survival

router = APIRouter(tags=["survival"])


class SurvivalRequest(BaseModel):
    vision: VisionResult
    sensors: SensorInput


@router.post("/survival", response_model=SurvivalResponse)
async def survival(req: SurvivalRequest) -> SurvivalResponse:
    try:
        inp = SurvivalInputs(
            disease=req.vision.disease,
            disease_confidence=req.vision.confidence,
            stress_hint=req.vision.stress_hint,
            soil_moisture=req.sensors.soil_moisture,
            temperature_c=req.sensors.temperature,
            humidity_pct=req.sensors.humidity,
            species=req.sensors.species,
        )
        result = SurvivalResponse.model_validate(compute_survival(inp))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result


@router.post("/survival/from-latest-sensor")
async def survival_from_latest(vision: VisionResult) -> SurvivalResponse:
    from routes.sensor import _latest

    if _latest is None:
        raise HTTPException(
            status_code=400,
            detail="No sensor data yet; POST /sensor first or use /survival with full body.",
        )
    req = SurvivalRequest(
        vision=vision,
        sensors=SensorInput(
            soil_moisture=float(_latest["soil_moisture"]),
            temperature=float(_latest["temperature"]),
            humidity=float(_latest["humidity"]),
            species=_latest.get("species"),
        ),
    )
    return await survival(req)
