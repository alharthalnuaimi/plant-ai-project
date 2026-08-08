"""Training jobs repository — Postgres persistence (Task 4).

Follows the sensor_repo.py retry-decorated pattern.
"""

from __future__ import annotations

import logging
from typing import Any

from core.retry import with_retry
from db.connection import get_pool

log = logging.getLogger("plantvision.repo.training_jobs")


@with_retry(name="training_jobs_repo.insert", attempts=3, fallback=None)
async def insert_job(*, record: dict[str, Any]) -> str | None:
    pool = await get_pool()
    if pool is None:
        return None
    import json
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO public.training_jobs
                (id, dataset_batch_ids, target, status,
                 metrics_before, metrics_before_note, metrics_after,
                 weights_url, error_message, created_at, started_at, completed_at)
            VALUES ($1, $2::jsonb, $3, $4, $5::jsonb, $6, $7::jsonb, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            record["id"],
            json.dumps(record.get("dataset_batch_ids", [])),
            record.get("target", "local"),
            record.get("status", "queued"),
            json.dumps(record.get("metrics_before")) if record.get("metrics_before") else None,
            record.get("metrics_before_note"),
            json.dumps(record.get("metrics_after")) if record.get("metrics_after") else None,
            record.get("weights_url"),
            record.get("error_message"),
            record.get("created_at"),
            record.get("started_at"),
            record.get("completed_at"),
        )
        return str(row["id"]) if row else None


@with_retry(name="training_jobs_repo.update_status", attempts=3, fallback=False)
async def update_job_status(*, job_id: str, updates: dict[str, Any]) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    import json
    async with pool.acquire() as conn:
        # Build dynamic SET clause
        set_parts = []
        params: list[Any] = [job_id]
        idx = 2
        for key, val in updates.items():
            if key in ("metrics_after", "metrics_before"):
                set_parts.append(f"{key} = ${idx}::jsonb")
                params.append(json.dumps(val) if val else None)
            else:
                set_parts.append(f"{key} = ${idx}")
                params.append(val)
            idx += 1

        if not set_parts:
            return True

        query = f"UPDATE public.training_jobs SET {', '.join(set_parts)} WHERE id = $1"
        await conn.execute(query, *params)
        return True


@with_retry(name="training_jobs_repo.list_jobs", attempts=3, fallback=[])
async def list_jobs(*, status: str | None = None, target: str | None = None) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        query = "SELECT * FROM public.training_jobs WHERE 1=1"
        params: list[Any] = []
        idx = 1
        if status:
            query += f" AND status = ${idx}"
            params.append(status)
            idx += 1
        if target:
            query += f" AND target = ${idx}"
            params.append(target)
            idx += 1
        query += " ORDER BY created_at DESC"
        rows = await conn.fetch(query, *params)
        return [dict(r) for r in rows]
