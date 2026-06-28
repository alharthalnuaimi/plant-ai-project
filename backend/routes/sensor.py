from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query

from repositories import sensor_repo
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

log = logging.getLogger("plantvision.sensor")

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


def _row_to_reading(row: dict[str, Any]) -> SensorReading | None:
    """Rebuild a SensorReading from a sensor_readings DB row.

    Status fields are re-derived from raw values (deterministic), and the
    original DB timestamp (`recorded_at`) is preserved so freshness math
    stays accurate after a backend restart.
    """

    try:
        payload = SensorInput(
            user_id=row.get("user_slug") or DEFAULT_USER_ID,
            zone_id=row.get("zone_slug") or DEFAULT_ZONE_ID,
            device_id=row.get("device_slug") or DEFAULT_DEVICE_ID,
            air_temperature=float(row["air_temp"]) if row.get("air_temp") is not None else None,
            air_humidity=float(row["air_humidity"]) if row.get("air_humidity") is not None else None,
            light_lux=float(row["lux"]) if row.get("lux") is not None else None,
            soil_temperature=float(row["soil_temp"]) if row.get("soil_temp") is not None else None,
            soil_humidity=float(row["soil_moisture"]) if row.get("soil_moisture") is not None else None,
            soil_ph=float(row["ph"]) if row.get("ph") is not None else None,
            soil_ec=float(row["ec"]) if row.get("ec") is not None else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("Could not rebuild SensorReading from DB row: %s", exc)
        return None

    reading = process_sensor_reading(payload)

    recorded_at = row.get("recorded_at")
    if isinstance(recorded_at, datetime):
        ts = recorded_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        reading = reading.model_copy(update={"timestamp": ts})
    return reading


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

    # Postgres fallback: in-memory cache is wiped on backend restart. If
    # persistence is enabled, hydrate the latest reading from the DB so
    # the API surface stays consistent across restarts.
    if reading is None:
        try:
            row = await sensor_repo.latest_for_device(device_id)
        except Exception as exc:  # noqa: BLE001 — never fail this endpoint
            log.warning("DB hydration for /sensor/latest failed: %s", exc)
            row = None
        if row:
            reading = _row_to_reading(row)
            if reading is not None:
                save_reading(reading)  # warm the in-memory cache

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
