"""Scan metrics repository — Postgres persistence (Task 4).

Follows the sensor_repo.py retry-decorated pattern.
"""

from __future__ import annotations

import logging
from typing import Any

from core.retry import with_retry
from db.connection import get_pool

log = logging.getLogger("plantvision.repo.metrics")


@with_retry(name="metrics_repo.insert", attempts=3, fallback=False)
async def insert_metric(*, inference_ms: float, model_source: str, image_size: list | None) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    import json
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.scan_metrics (inference_ms, model_source, image_size)
            VALUES ($1, $2, $3::jsonb)
            """,
            inference_ms, model_source,
            json.dumps(image_size) if image_size else None,
        )
        return True


@with_retry(name="metrics_repo.recent", attempts=3, fallback=[])
async def recent_metrics(*, limit: int = 100) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM public.scan_metrics ORDER BY recorded_at DESC LIMIT $1",
            limit,
        )
        return [dict(r) for r in rows]
