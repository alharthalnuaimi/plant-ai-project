from __future__ import annotations

import time
from datetime import datetime

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


def _age_seconds(iso_ts: str) -> float | None:
    try:
        return time.time() - datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _freshness_label(age: float | None) -> str:
    """Mirror analytics_store._freshness (live ≤30s, stale ≤300s, else offline)."""

    if age is None:
        return "offline"
    if age <= 30:
        return "live"
    if age <= 300:
        return "stale"
    return "offline"


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
        return SensorLatestResponse(
            ok=True, source="none", reading=None, age_seconds=None, freshness="none"
        )
    age = _age_seconds(reading.timestamp)
    return SensorLatestResponse(
        ok=True,
        source="live",
        reading=reading,
        age_seconds=round(age, 2) if age is not None else None,
        freshness=_freshness_label(age),
    )
