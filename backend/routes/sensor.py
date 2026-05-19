from __future__ import annotations

from fastapi import APIRouter, Query

from schemas.sensors import SensorInput, SensorLatestResponse, SensorReading
from services import analytics_store
from services.sensor_processing import process_sensor_reading
from services.sensor_store import (
    DEFAULT_DEVICE_ID,
    DEFAULT_USER_ID,
    DEFAULT_ZONE_ID,
    get_latest,
    save_reading,
)

router = APIRouter(tags=["sensor"])


@router.post("/sensor", response_model=SensorReading)
async def post_sensor(payload: SensorInput) -> SensorReading:
    reading = process_sensor_reading(payload)
    save_reading(reading)
    analytics_store.record_sensor(reading)
    return reading


@router.get("/sensor/latest", response_model=SensorLatestResponse)
async def sensor_latest(
    user_id: str = Query(default=DEFAULT_USER_ID, description="User id"),
    zone_id: str = Query(default=DEFAULT_ZONE_ID, description="Growing zone id"),
    device_id: str = Query(default=DEFAULT_DEVICE_ID, description="ESP32 / sensor node id"),
) -> SensorLatestResponse:
    reading = get_latest(user_id=user_id, zone_id=zone_id, device_id=device_id)
    if reading is None:
        return SensorLatestResponse(ok=True, source="none", reading=None)
    return SensorLatestResponse(ok=True, source="live", reading=reading)
