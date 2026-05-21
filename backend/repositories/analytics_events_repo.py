"""Analytics events repository (activity feed persistence)."""

from __future__ import annotations

import json
import logging
from typing import Any

from db.connection import get_pool

log = logging.getLogger("plantvision.repo.events")


async def insert_event(
    *,
    event_type: str,
    message: str,
    category: str | None = None,
    title: str | None = None,
    zone_slug: str | None = None,
    device_slug: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    payload_json = json.dumps(payload or {})
    try:
        async with pool.acquire() as conn:
            zone_id = None
            device_id = None
            if zone_slug:
                zone_id = await conn.fetchval(
                    "select id from public.zones where slug = $1", zone_slug
                )
            if device_slug:
                device_id = await conn.fetchval(
                    "select id from public.devices where slug = $1", device_slug
                )
            await conn.execute(
                """
                insert into public.analytics_events
                    (event_type, message, category, title,
                     zone_slug, device_slug, zone_id, device_id, payload_json)
                values ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
                """,
                event_type, message, category, title,
                zone_slug, device_slug, zone_id, device_id, payload_json,
            )
            return True
    except Exception as exc:  # noqa: BLE001
        log.warning("insert_event failed: %s", exc)
        return False


async def recent(limit: int = 30) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select * from public.analytics_events
                order by created_at desc
                limit $1
                """,
                limit,
            )
            return [dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("recent failed: %s", exc)
        return []
