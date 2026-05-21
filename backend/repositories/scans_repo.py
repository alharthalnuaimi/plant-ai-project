"""Scan results repository."""

from __future__ import annotations

import json
import logging
from typing import Any

from db.connection import get_pool

log = logging.getLogger("plantvision.repo.scans")


async def insert_scan(
    *,
    user_slug: str,
    zone_slug: str,
    device_slug: str | None,
    image_path: str | None,
    prediction_class: str | None,
    disease_type: str | None,
    disease: str,
    confidence: float,
    accepted: bool,
    inference_ms: float,
    health_score: int | None,
    risk_level: str | None,
    survival_score: int | None,
    recommendation: str | None,
    model_name: str | None,
    model_version: str | None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    meta_json = json.dumps(metadata or {})
    try:
        async with pool.acquire() as conn:
            zone_id = await conn.fetchval(
                "select id from public.zones where slug = $1", zone_slug
            )
            device_id = None
            if device_slug:
                device_id = await conn.fetchval(
                    "select id from public.devices where slug = $1", device_slug
                )
            await conn.execute(
                """
                insert into public.scan_results
                    (zone_id, device_id, zone_slug, device_slug, user_slug,
                     image_path, prediction_class, disease_type, disease, confidence,
                     accepted, inference_ms, health_score, risk_level,
                     survival_score, recommendation, model_name, model_version,
                     metadata_json)
                values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19::jsonb)
                """,
                zone_id, device_id, zone_slug, device_slug, user_slug,
                image_path, prediction_class, disease_type, disease, confidence,
                accepted, inference_ms, health_score, risk_level,
                survival_score, recommendation, model_name, model_version,
                meta_json,
            )
            return True
    except Exception as exc:  # noqa: BLE001
        log.warning("insert_scan failed: %s", exc)
        return False


async def recent(limit: int = 20, zone_slug: str | None = None) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            if zone_slug:
                rows = await conn.fetch(
                    """
                    select * from public.scan_results
                    where zone_slug = $1
                    order by created_at desc
                    limit $2
                    """,
                    zone_slug, limit,
                )
            else:
                rows = await conn.fetch(
                    """
                    select * from public.scan_results
                    order by created_at desc
                    limit $1
                    """,
                    limit,
                )
            return [dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("recent failed: %s", exc)
        return []
