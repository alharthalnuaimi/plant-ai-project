from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from schemas.contracts import SurvivalSensorInput, SurvivalResponse, VisionResult
from services.survival import SurvivalInputs, compute_survival

router = APIRouter(tags=["survival"])


class SurvivalRequest(BaseModel):
    vision: VisionResult
    sensors: SurvivalSensorInput


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
    from services.sensor_store import DEFAULT_DEVICE_ID, get_latest

    latest = get_latest(
        user_id=vision.user_id,
        zone_id=vision.zone_id,
        device_id=DEFAULT_DEVICE_ID,
    )
    if latest is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "No sensor data for this user/zone/device yet; "
                "POST /sensor first or use /survival with full body."
            ),
        )
    req = SurvivalRequest(
        vision=vision,
        sensors=SurvivalSensorInput(
            soil_moisture=latest.soil_humidity,
            temperature=latest.air_temperature,
            humidity=latest.air_humidity,
            species=latest.zone_id,
        ),
    )
    return await survival(req)
