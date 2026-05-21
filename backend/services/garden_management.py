"""
Garden management service — zones & devices CRUD.

Hybrid store: when Postgres is enabled, reads/writes go to the DB; when
not, an in-memory dict keeps the API contract identical so the frontend
still works in offline / demo mode.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config.settings import SETTINGS
from db.connection import is_postgres_enabled
from repositories import devices_repo, zones_repo

# -------- in-memory fallback stores (preserve current MVP behaviour) ----
_zones_mem: dict[str, dict[str, Any]] = {}
_devices_mem: dict[str, dict[str, Any]] = {}


def _seed_mem_defaults() -> None:
    if _zones_mem:
        return
    now = datetime.now(timezone.utc).isoformat()
    defaults = [
        ("zone_alpha", "Zone Alpha", "HEALTHY", 32.0853, 34.7818, 48),
        ("zone_beta", "Zone Beta", "WARNING", 32.0900, 34.7900, 36),
        ("zone_gamma", "Zone Gamma", "HEALTHY", 32.0800, 34.7700, 24),
    ]
    for slug, name, status, lat, lng, count in defaults:
        _zones_mem[slug] = {
            "id": None,
            "slug": slug,
            "name": name,
            "status": status,
            "latitude": lat,
            "longitude": lng,
            "plants_count": count,
            "created_at": now,
            "updated_at": now,
        }


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for k, v in list(out.items()):
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    if "id" in out and out["id"] is not None:
        out["id"] = str(out["id"])
    return out


# ---------- zones -------------------------------------------------------

async def list_zones() -> tuple[str, list[dict[str, Any]]]:
    if SETTINGS.use_postgres and is_postgres_enabled():
        rows = await zones_repo.list_zones()
        if rows:
            return "postgres", [_normalize_row(r) for r in rows]
    _seed_mem_defaults()
    return "memory", list(_zones_mem.values())


async def upsert_zone(payload: dict[str, Any]) -> dict[str, Any]:
    slug = payload["slug"]
    if SETTINGS.use_postgres and is_postgres_enabled():
        row = await zones_repo.upsert_zone(
            slug=slug,
            name=payload["name"],
            status=payload.get("status", "HEALTHY"),
            latitude=payload.get("latitude"),
            longitude=payload.get("longitude"),
            plants_count=payload.get("plants_count", 0),
        )
        if row:
            return _normalize_row(row)
    _seed_mem_defaults()
    now = datetime.now(timezone.utc).isoformat()
    existing = _zones_mem.get(slug, {})
    saved = {
        "id": existing.get("id"),
        "slug": slug,
        "name": payload["name"],
        "status": payload.get("status", "HEALTHY"),
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "plants_count": payload.get("plants_count", 0),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    _zones_mem[slug] = saved
    return saved


async def delete_zone(slug: str) -> bool:
    deleted = False
    if SETTINGS.use_postgres and is_postgres_enabled():
        deleted = await zones_repo.delete_zone(slug) or deleted
    if slug in _zones_mem:
        _zones_mem.pop(slug, None)
        deleted = True
    return deleted


# ---------- devices -----------------------------------------------------

async def list_devices(zone_slug: str | None = None) -> tuple[str, list[dict[str, Any]]]:
    if SETTINGS.use_postgres and is_postgres_enabled():
        rows = await devices_repo.list_devices(zone_slug)
        if rows:
            return "postgres", [_normalize_row(r) for r in rows]
    items = list(_devices_mem.values())
    if zone_slug:
        items = [d for d in items if d.get("zone_slug") == zone_slug]
    return "memory", items


async def upsert_device(payload: dict[str, Any]) -> dict[str, Any]:
    slug = payload["slug"]
    if SETTINGS.use_postgres and is_postgres_enabled():
        row = await devices_repo.upsert_device(
            slug=slug,
            device_name=payload["device_name"],
            zone_slug=payload.get("zone_slug"),
            ip_address=payload.get("ip_address"),
            status=payload.get("status", "OFFLINE"),
            metadata=payload.get("metadata") or {},
        )
        if row:
            normalized = _normalize_row(row)
            normalized["zone_slug"] = payload.get("zone_slug")
            return normalized
    now = datetime.now(timezone.utc).isoformat()
    existing = _devices_mem.get(slug, {})
    saved = {
        "id": existing.get("id"),
        "slug": slug,
        "device_name": payload["device_name"],
        "zone_slug": payload.get("zone_slug"),
        "ip_address": payload.get("ip_address"),
        "status": payload.get("status", "OFFLINE"),
        "metadata": payload.get("metadata") or {},
        "last_seen": existing.get("last_seen"),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    _devices_mem[slug] = saved
    return saved


async def delete_device(slug: str) -> bool:
    deleted = False
    if SETTINGS.use_postgres and is_postgres_enabled():
        deleted = await devices_repo.delete_device(slug) or deleted
    if slug in _devices_mem:
        _devices_mem.pop(slug, None)
        deleted = True
    return deleted
