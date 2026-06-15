"""CRUD routes for ESP32 / sensor devices.

Phase 4 (B2) — adds two additive endpoints that reuse data
``/health/sensor`` and the existing CRUD already build:

* ``POST /devices/register`` — thin upsert wrapper that only requires
  ``{slug, label?, zone_slug?}``. ESP32 firmware can call this on boot
  without having to know the full DeviceIn shape.
* ``GET /devices/diagnostics`` — per-device freshness, retry counters,
  reachability, last error. Returned in a flat shape the Settings page
  can render directly.

Neither endpoint changes any existing response shape — they are purely
additive surface for the new Settings page section and future ops UIs.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from config.settings import SETTINGS
from core.retry import get_recent_retry_events, get_retry_stats
from db.connection import ping
from repositories import devices_repo
from schemas.garden_management import DeviceIn, DeviceListResponse, DeviceOut
from services import garden_management, sensor_store

router = APIRouter(prefix="/devices", tags=["devices"])


# ---------------------------------------------------------------------------
# Phase 4 (B2) — register + diagnostics schemas
# ---------------------------------------------------------------------------


class DeviceRegisterIn(BaseModel):
    """Minimal payload an ESP32 firmware needs to register itself.

    Mirrors the columns in ``public.devices`` but with friendlier names:
    ``label`` becomes ``device_name`` on the way down.
    """

    slug: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=128)
    zone_slug: str | None = Field(default=None, max_length=64)


class DeviceDiagnostic(BaseModel):
    slug: str
    last_seen_at: str | None = None
    age_seconds: float | None = None
    freshness: Literal["live", "stale", "offline"] = "offline"
    retry_counters: dict[str, int] = Field(default_factory=dict)
    reachable: bool = False
    last_error: str | None = None
    zone_slug: str | None = None
    source: str = "memory"


class DeviceDiagnosticsResponse(BaseModel):
    source: str = "live"
    count: int = 0
    devices: list[DeviceDiagnostic] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Existing endpoints (unchanged response shape)
# ---------------------------------------------------------------------------


@router.get("", response_model=DeviceListResponse)
async def list_devices(zone: str | None = None) -> DeviceListResponse:
    source, items = await garden_management.list_devices(zone_slug=zone)
    return DeviceListResponse(source=source, devices=[DeviceOut(**d) for d in items])


@router.post("", response_model=DeviceOut)
async def upsert_device(payload: DeviceIn) -> DeviceOut:
    saved = await garden_management.upsert_device(payload.model_dump())
    return DeviceOut(**saved)


# ---------------------------------------------------------------------------
# Phase 4 (B2) — additive routes
# ---------------------------------------------------------------------------
# IMPORTANT: declare literal paths (/register, /diagnostics) BEFORE the
# parameterized `/{slug}` routes so FastAPI's prefix-matching does not
# treat them as a slug value.


@router.post("/register", response_model=DeviceOut)
async def register_device(payload: DeviceRegisterIn) -> DeviceOut:
    """Phase 4 — thin self-registration endpoint for ESP32 firmware.

    Upserts a device with a sensible default ``device_name`` (falling
    back to the slug itself when ``label`` is missing) and the default
    ``OFFLINE`` status. The first ``POST /sensor`` from this slug will
    flip it to ``ONLINE`` via ``devices_repo.mark_seen``.
    """

    data: dict[str, Any] = {
        "slug": payload.slug.strip(),
        "device_name": (payload.label or payload.slug).strip() or payload.slug.strip(),
        "zone_slug": (payload.zone_slug or "").strip() or None,
        "ip_address": None,
        "status": "OFFLINE",
        "metadata": {"registered_via": "/devices/register"},
    }
    saved = await garden_management.upsert_device(data)
    return DeviceOut(**saved)


@router.get("/diagnostics", response_model=DeviceDiagnosticsResponse)
async def device_diagnostics() -> DeviceDiagnosticsResponse:
    """Per-device freshness + retry counters + reachability.

    Reuses the same freshness rules as ``/health/sensor`` (live ≤30s,
    stale ≤300s, else offline) but folds in retry telemetry from
    ``core.retry`` so a single GET tells the Settings page everything
    it needs about each ESP32 node.
    """

    # ---- 1) gather raw device rows (DB-known + memory-cached) -----------
    seen_slugs: set[str] = set()
    devices_meta: dict[str, dict[str, Any]] = {}

    pg_ok = await ping() if SETTINGS.use_postgres else False
    if SETTINGS.use_postgres and pg_ok:
        try:
            for row in await devices_repo.list_devices():
                slug = (row.get("slug") or "").strip()
                if slug and slug not in seen_slugs:
                    seen_slugs.add(slug)
                    devices_meta[slug] = {
                        "zone_slug": row.get("zone_slug"),
                        "source": "postgres",
                        "last_seen_at": row.get("last_seen"),
                    }
        except Exception:  # noqa: BLE001 — diagnostics endpoint must never crash
            pass

    for reading in sensor_store.list_all_readings():
        slug = reading.device_id
        if slug and slug not in seen_slugs:
            seen_slugs.add(slug)
            devices_meta[slug] = {
                "zone_slug": reading.zone_id,
                "source": "memory",
                "last_seen_at": reading.timestamp,
            }

    # ---- 2) retry telemetry snapshot ------------------------------------
    raw_stats = get_retry_stats()
    failed = 0
    retries = 0
    for bucket in raw_stats.values():
        if isinstance(bucket, dict):
            failed += int(bucket.get("failures", 0) or 0)
            retries += int(bucket.get("retries", 0) or 0)
    retry_counters = {"failed": failed, "retries": retries}

    recent_events = get_recent_retry_events(limit=20)
    last_error = next(
        (e.get("message") for e in reversed(recent_events) if e.get("outcome") == "failed"),
        None,
    )

    # ---- 3) build per-device freshness rows -----------------------------
    rows: list[DeviceDiagnostic] = []
    for slug in sorted(seen_slugs):
        meta = devices_meta.get(slug, {})
        last_seen_iso, age = _resolve_last_seen(slug, meta)
        fresh = _freshness(age)
        rows.append(
            DeviceDiagnostic(
                slug=slug,
                last_seen_at=last_seen_iso,
                age_seconds=age,
                freshness=fresh,
                retry_counters=dict(retry_counters),
                reachable=fresh in ("live", "stale"),
                last_error=last_error,
                zone_slug=meta.get("zone_slug"),
                source=meta.get("source", "memory"),
            )
        )

    return DeviceDiagnosticsResponse(
        source="live",
        count=len(rows),
        devices=rows,
    )


# ---------------------------------------------------------------------------
# Phase 4 (B2) — small helpers (kept local so tests can import them directly)
# ---------------------------------------------------------------------------


def _freshness(age: float | None) -> Literal["live", "stale", "offline"]:
    """Mirror ``analytics_store._freshness`` / ``health_route._freshness``."""

    if age is None:
        return "offline"
    if age <= 30:
        return "live"
    if age <= 300:
        return "stale"
    return "offline"


def _resolve_last_seen(slug: str, meta: dict[str, Any]) -> tuple[str | None, float | None]:
    """Resolve (iso_ts, age_seconds) for a device.

    Prefers the in-memory sensor cache (cheap + always fresh); falls
    back to the device row's ``last_seen`` field when no readings have
    been received in this process.
    """

    import time as _time
    from datetime import datetime, timezone

    cached = next(
        (r for r in sensor_store.list_all_readings() if r.device_id == slug),
        None,
    )
    if cached is not None:
        iso = cached.timestamp
        age = _iso_age(iso)
        return iso, age

    raw_last = meta.get("last_seen_at")
    if isinstance(raw_last, datetime):
        if raw_last.tzinfo is None:
            raw_last = raw_last.replace(tzinfo=timezone.utc)
        iso = raw_last.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        age = max(0.0, _time.time() - raw_last.timestamp())
        return iso, round(age, 2)
    if isinstance(raw_last, str):
        return raw_last, _iso_age(raw_last)
    return None, None


def _iso_age(iso_ts: str | None) -> float | None:
    """Seconds since the given ISO-8601 timestamp, or None on parse error."""

    import time as _time
    from datetime import datetime

    if not iso_ts:
        return None
    try:
        return round(_time.time() - datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).timestamp(), 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Slug-parameterized routes (declared LAST so /register and /diagnostics
# match first).
# ---------------------------------------------------------------------------


@router.get("/{slug}", response_model=DeviceOut)
async def get_device(slug: str) -> DeviceOut:
    """Single-device fetch.

    Hits the same garden_management.list_devices path so memory and
    Postgres fallback semantics are identical to the list endpoint.
    """

    slug = (slug or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    _, items = await garden_management.list_devices()
    for item in items:
        if (item.get("slug") or "") == slug:
            return DeviceOut(**item)
    raise HTTPException(status_code=404, detail="Device not found")


@router.put("/{slug}", response_model=DeviceOut)
async def update_device(slug: str, payload: DeviceIn) -> DeviceOut:
    data = payload.model_dump()
    data["slug"] = slug
    saved = await garden_management.upsert_device(data)
    return DeviceOut(**saved)


@router.delete("/{slug}")
async def delete_device(slug: str) -> dict[str, bool]:
    ok = await garden_management.delete_device(slug)
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"ok": True}
