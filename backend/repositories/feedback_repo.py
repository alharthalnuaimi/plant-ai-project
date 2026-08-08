"""Scan feedback repository — Postgres persistence (Task 4).

Follows the sensor_repo.py retry-decorated pattern. Falls back gracefully
when the pool is unavailable (PERSISTENCE_BACKEND=memory).
"""

from __future__ import annotations

import logging
from typing import Any

from core.retry import with_retry
from db.connection import get_pool

log = logging.getLogger("plantvision.repo.feedback")


@with_retry(name="feedback_repo.insert", attempts=3, fallback=None)
async def insert_feedback(*, record: dict[str, Any]) -> str | None:
    pool = await get_pool()
    if pool is None:
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO public.scan_feedback
                (id, image_ref, yolo_label, yolo_confidence,
                 gemini_label, gemini_agrees, reasoning, reviewed, confirmed_label, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id
            """,
            record["id"], record.get("image_ref"), record.get("yolo_label"),
            record.get("yolo_confidence"), record.get("gemini_label"),
            record.get("gemini_agrees"), record.get("reasoning"),
            record.get("reviewed", False), record.get("confirmed_label"),
            record.get("created_at"),
        )
        return str(row["id"]) if row else None


@with_retry(name="feedback_repo.confirm", attempts=3, fallback=False)
async def confirm_feedback(*, feedback_id: str, confirmed_label: str) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE public.scan_feedback
            SET reviewed = TRUE, confirmed_label = $2, reviewed_at = now()
            WHERE id = $1
            """,
            feedback_id, confirmed_label,
        )
        return True


@with_retry(name="feedback_repo.list_all", attempts=3, fallback=[])
async def list_all() -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM public.scan_feedback ORDER BY created_at DESC LIMIT 200"
        )
        return [dict(r) for r in rows]


@with_retry(name="feedback_repo.list_pending", attempts=3, fallback=[])
async def list_pending() -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM public.scan_feedback WHERE reviewed = FALSE ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]
