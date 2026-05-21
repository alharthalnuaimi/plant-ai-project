"""
Persistence orchestration layer.

This is the bridge between in-memory MVP stores and the new repository
layer. It exposes small async helpers used by routes/services so the
existing synchronous code paths stay simple.

Every helper is safe to call even when the database is offline — it
silently no-ops and the in-memory stores continue to serve reads.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from config.settings import SETTINGS
from repositories import (
    analytics_events_repo,
    devices_repo,
    scans_repo,
    sensor_repo,
)
from schemas.contracts import VisionResult
from schemas.sensors import SensorReading

log = logging.getLogger("plantvision.persistence")


def _fire_and_forget(coro) -> None:
    """Run a coroutine without awaiting it (best-effort persistence).

    If no event loop is running (e.g. unit test), we silently drop the
    work — persistence is never on the critical path.
    """

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(coro)


async def persist_scan_async(result: VisionResult) -> None:
    if not (SETTINGS.use_postgres and SETTINGS.persist_scan_history):
        return
    h = result.health
    meta = dict(result.metadata or {})
    image_path = meta.pop("saved_path", None) if isinstance(meta, dict) else None
    await scans_repo.insert_scan(
        user_slug=result.user_id,
        zone_slug=result.zone_id,
        device_slug=meta.get("device_id") if isinstance(meta, dict) else None,
        image_path=image_path,
        prediction_class=result.class_name or None,
        disease_type=result.disease_type or None,
        disease=result.disease,
        confidence=float(result.confidence),
        accepted=bool(result.accepted),
        inference_ms=float(result.inference_ms),
        health_score=int(h.plant_health) if h else None,
        risk_level=h.disease_risk if h else None,
        survival_score=int(h.survival_chance) if h else None,
        recommendation=h.recommendation if h else None,
        model_name=result.model_name,
        model_version=result.model_version,
        metadata=meta if isinstance(meta, dict) else {},
    )


def persist_scan(result: VisionResult) -> None:
    _fire_and_forget(persist_scan_async(result))


async def persist_sensor_async(reading: SensorReading) -> None:
    if not (SETTINGS.use_postgres and SETTINGS.persist_sensor_history):
        return
    await sensor_repo.insert_reading(
        user_slug=reading.user_id,
        zone_slug=reading.zone_id,
        device_slug=reading.device_id,
        air_temp=float(reading.air_temperature),
        air_humidity=float(reading.air_humidity),
        soil_temp=float(reading.soil_temperature),
        soil_moisture=float(reading.soil_humidity),
        ph=float(reading.soil_ph),
        ec=float(reading.soil_ec),
        lux=float(reading.light_lux),
    )
    await devices_repo.mark_seen(reading.device_id)


def persist_sensor(reading: SensorReading) -> None:
    _fire_and_forget(persist_sensor_async(reading))


async def persist_event_async(
    *,
    event_type: str,
    message: str,
    zone_slug: str | None = None,
    device_slug: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    if not (SETTINGS.use_postgres and SETTINGS.persist_events):
        return
    await analytics_events_repo.insert_event(
        event_type=event_type,
        message=message,
        zone_slug=zone_slug,
        device_slug=device_slug,
        payload=payload,
    )


def persist_event(
    *,
    event_type: str,
    message: str,
    zone_slug: str | None = None,
    device_slug: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    _fire_and_forget(
        persist_event_async(
            event_type=event_type,
            message=message,
            zone_slug=zone_slug,
            device_slug=device_slug,
            payload=payload,
        )
    )
