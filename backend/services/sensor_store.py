"""In-memory latest ESP sensor reading (MVP — replace with DB later)."""

from __future__ import annotations

from schemas.sensors import SensorReading

_latest: SensorReading | None = None


def save_reading(reading: SensorReading) -> None:
    global _latest
    _latest = reading


def get_latest() -> SensorReading | None:
    return _latest
