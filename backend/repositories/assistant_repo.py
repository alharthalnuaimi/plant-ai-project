"""Assistant Q/A log repository (optional)."""

from __future__ import annotations

import logging
from typing import Any

from db.connection import get_pool

log = logging.getLogger("plantvision.repo.assistant")


async def log_interaction(
    *,
    question: str,
    response: str,
    zone_slug: str | None = None,
) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            zone_id = None
            if zone_slug:
                zone_id = await conn.fetchval(
                    "select id from public.zones where slug = $1", zone_slug
                )
            await conn.execute(
                """
                insert into public.assistant_logs (question, response, zone_slug, zone_id)
                values ($1,$2,$3,$4)
                """,
                question, response, zone_slug, zone_id,
            )
            return True
    except Exception as exc:  # noqa: BLE001
        log.warning("log_interaction failed: %s", exc)
        return False


async def recent(limit: int = 20) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select * from public.assistant_logs
                order by created_at desc
                limit $1
                """,
                limit,
            )
            return [dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("recent failed: %s", exc)
        return []
