"""Sensor readings repository (time-series writes + recent queries).

Phase 3 hardening: each Postgres call is now wrapped by ``with_retry`` so
transient pgbouncer / network blips trigger bounded exponential-backoff
retries instead of silently logging once and returning. The public function
contract is unchanged — repositories remain best-effort and fall back to
``False`` / ``None`` / ``[]`` when all retries are exhausted.
"""

from __future__ import annotations

import logging
from typing import Any

from core.retry import with_retry
from db.connection import get_pool

log = logging.getLogger("plantvision.repo.sensor")


@with_retry(name="sensor_repo.insert_reading", attempts=3, fallback=False)
async def insert_reading(
    *,
    user_slug: str,
    zone_slug: str,
    device_slug: str,
    air_temp: float | None,
    air_humidity: float | None,
    soil_temp: float | None,
    soil_moisture: float | None,
    ph: float | None,
    ec: float | None,
    lux: float | None,
) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    # Coalesce None → 0.0 so the NOT NULL DB columns stay happy.
    _air_temp = air_temp if air_temp is not None else 0.0
    _air_humidity = air_humidity if air_humidity is not None else 0.0
    _soil_temp = soil_temp if soil_temp is not None else 0.0
    _soil_moisture = soil_moisture if soil_moisture is not None else 0.0
    _ph = ph if ph is not None else 0.0
    _ec = ec if ec is not None else 0.0
    _lux = lux if lux is not None else 0.0
    async with pool.acquire() as conn:
        device_id = await conn.fetchval(
            "select id from public.devices where slug = $1", device_slug
        )
        await conn.execute(
            """
            insert into public.sensor_readings
                (device_id, zone_slug, device_slug, user_slug,
                 air_temp, air_humidity, soil_temp, soil_moisture,
                 ph, ec, lux)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,
            device_id, zone_slug, device_slug, user_slug,
            _air_temp, _air_humidity, _soil_temp, _soil_moisture,
            _ph, _ec, _lux,
        )
    return True


@with_retry(name="sensor_repo.recent_for_zone", attempts=2, fallback=[])
async def recent_for_zone(zone_slug: str, limit: int = 50) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select * from public.sensor_readings
            where zone_slug = $1
            order by recorded_at desc
            limit $2
            """,
            zone_slug, limit,
        )
        return [dict(r) for r in rows]


@with_retry(name="sensor_repo.latest_for_device", attempts=3, fallback=None)
async def latest_for_device(device_slug: str) -> dict[str, Any] | None:
    pool = await get_pool()
    if pool is None:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            select * from public.sensor_readings
            where device_slug = $1
            order by recorded_at desc
            limit 1
            """,
            device_slug,
        )
        return dict(row) if row else None


@with_retry(name="sensor_repo.recent_readings", attempts=2, fallback=[])
async def recent_readings(limit: int = 100) -> list[dict[str, Any]]:
    """Retrieve recent readings across all devices, ordered oldest to newest (recorded_at asc) for sparkline history."""
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select * from (
                select * from public.sensor_readings
                order by recorded_at desc
                limit $1
            ) sub
            order by recorded_at asc
            """,
            limit,
        )
        return [dict(r) for r in rows]
