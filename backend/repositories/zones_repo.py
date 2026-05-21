"""Zone CRUD repository (Postgres-backed, memory-safe fallback)."""

from __future__ import annotations

import logging
from typing import Any

from db.connection import get_pool

log = logging.getLogger("plantvision.repo.zones")


async def list_zones() -> list[dict[str, Any]]:
    pool = await get_pool()
    if pool is None:
        return []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                select id, slug, name, status, latitude, longitude,
                       plants_count, created_at, updated_at
                from public.zones
                order by created_at asc
                """
            )
            return [dict(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        log.warning("list_zones failed: %s", exc)
        return []


async def get_zone_by_slug(slug: str) -> dict[str, Any] | None:
    pool = await get_pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "select * from public.zones where slug = $1 limit 1",
                slug,
            )
            return dict(row) if row else None
    except Exception as exc:  # noqa: BLE001
        log.warning("get_zone_by_slug failed: %s", exc)
        return None


async def upsert_zone(
    *,
    slug: str,
    name: str,
    status: str = "HEALTHY",
    latitude: float | None = None,
    longitude: float | None = None,
    plants_count: int = 0,
) -> dict[str, Any] | None:
    pool = await get_pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                insert into public.zones (slug, name, status, latitude, longitude, plants_count)
                values ($1, $2, $3, $4, $5, $6)
                on conflict (slug) do update set
                    name = excluded.name,
                    status = excluded.status,
                    latitude = excluded.latitude,
                    longitude = excluded.longitude,
                    plants_count = excluded.plants_count
                returning *
                """,
                slug, name, status, latitude, longitude, plants_count,
            )
            return dict(row) if row else None
    except Exception as exc:  # noqa: BLE001
        log.warning("upsert_zone failed: %s", exc)
        return None


async def delete_zone(slug: str) -> bool:
    pool = await get_pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            res = await conn.execute(
                "delete from public.zones where slug = $1", slug
            )
            return res.upper().startswith("DELETE 1")
    except Exception as exc:  # noqa: BLE001
        log.warning("delete_zone failed: %s", exc)
        return False
