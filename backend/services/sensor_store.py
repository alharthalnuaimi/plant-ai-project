"""In-memory sensor readings keyed by user_id → zone_id → device_id (MVP)."""

from __future__ import annotations

from schemas.sensors import SensorReading

DEFAULT_USER_ID = "demo_user"
DEFAULT_ZONE_ID = "zone_alpha"
DEFAULT_DEVICE_ID = "esp32_001"

# Internal composite key only — API always exposes user_id, zone_id, device_id separately.
_readings: dict[str, SensorReading] = {}


def composite_key(user_id: str, zone_id: str, device_id: str) -> str:
    """Internal lookup key, e.g. demo_user:zone_alpha:esp32_001"""
    return f"{user_id}:{zone_id}:{device_id}"


def save_reading(reading: SensorReading) -> None:
    key = composite_key(reading.user_id, reading.zone_id, reading.device_id)
    _readings[key] = reading


def get_latest(
    user_id: str = DEFAULT_USER_ID,
    zone_id: str = DEFAULT_ZONE_ID,
    device_id: str = DEFAULT_DEVICE_ID,
) -> SensorReading | None:
    key = composite_key(user_id, zone_id, device_id)
    return _readings.get(key)


def list_all_readings() -> list[SensorReading]:
    return list(_readings.values())
