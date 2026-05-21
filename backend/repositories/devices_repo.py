"""Device CRUD repository."""

from __future__ import annotations

import json
import logging
from typing import Any

from db.connection import get_pool

log = logging.getLogger("plantvision.repo.devices")


async def list_devices(zone_slug: str | None = None) -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            if zone_slug:
                rows = await conn.fetch(
                    """
                    select d.*, z.slug as zone_slug
                    from public.devices d
                    left join public.zones z on z.id = d.zone_id
                    where z.slug = $1
                    order by d.created_at asc
                    """,
                    zone_slug,
                )
            else:
                rows = await conn.fetch(
                    """
                    select d.*, z.slug as zone_slug
                    from public.devices d
                    left join public.zones z on z.id = d.zone_id
                    order by d.created_at asc
                    """
                )
            return [dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("list_devices failed: %s", exc)
        return []


async def upsert_device(
    *,
    slug: str,
    device_name: str,
    zone_slug: str | None = None,
    ip_address: str | None = None,
    status: str = "OFFLINE",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    pool = await get_pool()
    if pool is None:
        return None
    meta_json = json.dumps(metadata or {})
    try:
        async with pool.acquire() as conn:
            zone_id = None
            if zone_slug:
                zone_id = await conn.fetchval(
                    "select id from public.zones where slug = $1", zone_slug
                )
            row = await conn.fetchrow(
                """
                insert into public.devices
                    (slug, device_name, zone_id, ip_address, status, metadata_json)
                values ($1, $2, $3, $4, $5, $6::jsonb)
                on conflict (slug) do update set
                    device_name = excluded.device_name,
                    zone_id = excluded.zone_id,
                    ip_address = excluded.ip_address,
                    status = excluded.status,
                    metadata_json = excluded.metadata_json
                returning *
                """,
                slug, device_name, zone_id, ip_address, status, meta_json,
            )
            return dict(row) if row else None
    except Exception as exc:  # noqa: BLE001
        log.warning("upsert_device failed: %s", exc)
        return None


async def mark_seen(slug: str) -> None:
    pool = await get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                update public.devices
                set last_seen = now(), status = 'ONLINE'
                where slug = $1
                """,
                slug,
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("mark_seen failed: %s", exc)


async def delete_device(slug: str) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            res = await conn.execute(
                "delete from public.devices where slug = $1", slug
            )
            return res.upper().startswith("DELETE 1")
    except Exception as exc:  # noqa: BLE001
        log.warning("delete_device failed: %s", exc)
        return False
