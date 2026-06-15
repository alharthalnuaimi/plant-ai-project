"""
Audit log repository (Phase 3, Increment 5).

Backs the durable ``public.audit_log`` table introduced by migration
0003_audit_log.sql. Used by ``services.audit_log`` to persist operator-
facing events: retries, validation rejections, /predict and /report
invocations, /care lookups.

Best-effort by design: every helper degrades to ``False`` / ``[]`` /
``None`` on transient errors so a database hiccup never breaks the
calling request.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from core.retry import with_retry
from db.connection import get_pool

log = logging.getLogger("plantvision.repo.audit")


@with_retry(name="audit_repo.insert", attempts=3, fallback=False)
async def insert_audit(
    *,
    event_type: str,
    severity: str = "info",
    operation: str | None = None,
    request_id: str | None = None,
    actor: str | None = None,
    zone_slug: str | None = None,
    device_slug: str | None = None,
    plant_id: str | None = None,
    outcome: str | None = None,
    elapsed_ms: float | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    payload_json = json.dumps(payload or {})
    async with pool.acquire() as conn:
        await conn.execute(
            """
            insert into public.audit_log (
                event_type, severity, operation, request_id, actor,
                zone_slug, device_slug, plant_id, outcome,
                elapsed_ms, error_class, error_message, payload_json
            ) values (
                $1,$2,$3,$4,$5,
                $6,$7,$8,$9,
                $10,$11,$12,$13::jsonb
            )
            """,
            event_type, severity, operation, request_id, actor,
            zone_slug, device_slug, plant_id, outcome,
            elapsed_ms, error_class, error_message, payload_json,
        )
        return True


@with_retry(name="audit_repo.recent", attempts=2, fallback=[])
async def recent_audit(
    *,
    limit: int = 50,
    event_type: str | None = None,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    async with pool.acquire() as conn:
        if event_type and severity:
            rows = await conn.fetch(
                """
                select * from public.audit_log
                where event_type = $1 and severity = $2
                order by created_at desc
                limit $3
                """,
                event_type, severity, limit,
            )
        elif event_type:
            rows = await conn.fetch(
                """
                select * from public.audit_log
                where event_type = $1
                order by created_at desc
                limit $2
                """,
                event_type, limit,
            )
        elif severity:
            rows = await conn.fetch(
                """
                select * from public.audit_log
                where severity = $1
                order by created_at desc
                limit $2
                """,
                severity, limit,
            )
        else:
            rows = await conn.fetch(
                """
                select * from public.audit_log
                order by created_at desc
                limit $1
                """,
                limit,
            )
        return [dict(r) for r in rows]


@with_retry(name="audit_repo.purge_info_older_than", attempts=2, fallback=0)
async def purge_info_older_than(days: int = 14) -> int:
    """Delete info-severity audit rows older than ``days``. Returns row count."""

    pool = await get_pool()
    if pool is None:
        return 0
    async with pool.acquire() as conn:
        res = await conn.execute(
            """
            delete from public.audit_log
            where severity = 'info'
              and created_at < now() - ($1::int || ' days')::interval
            """,
            days,
        )
        try:
            return int(res.split()[-1])
        except (ValueError, IndexError):
            return 0
