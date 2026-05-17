from __future__ import annotations

from fastapi import APIRouter

from schemas.sensors import SensorInput, SensorLatestResponse, SensorReading
from services.sensor_processing import process_sensor_reading
from services.sensor_store import get_latest, save_reading

router = APIRouter(tags=["sensor"])


@router.post("/sensor", response_model=SensorReading)
async def post_sensor(payload: SensorInput) -> SensorReading:
    reading = process_sensor_reading(payload)
    save_reading(reading)
    return reading


@router.get("/sensor/latest", response_model=SensorLatestResponse)
async def sensor_latest() -> SensorLatestResponse:
    reading = get_latest()
    if reading is None:
        return SensorLatestResponse(ok=True, source="none", reading=None)
    return SensorLatestResponse(ok=True, source="live", reading=reading)
