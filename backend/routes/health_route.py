from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from fastapi import APIRouter, Query

from config.settings import SETTINGS
from core.retry import (
    count_validation_failures,
    get_recent_retry_events,
    get_retry_stats,
)
from db.connection import deployment_mode, ping
from repositories import devices_repo, sensor_repo
from schemas.health import (
    PlantHealthScore,
    SensorDeviceHealth,
    SensorHealthResponse,
)
from services import analytics_store, audit_log, sensor_store
from services.plant_health import compute_plant_health

log = logging.getLogger("plantvision.health")

router = APIRouter(tags=["health"])


@router.get("/health/plant", response_model=PlantHealthScore)
async def plant_health(
    user_id: str = Query(default="demo_user"),
    zone_id: str = Query(default="zone_alpha"),
    device_id: str = Query(default="esp32_001"),
) -> PlantHealthScore:
    uid = (user_id or "demo_user").strip() or "demo_user"
    zid = (zone_id or "zone_alpha").strip() or "zone_alpha"
    did = (device_id or "esp32_001").strip() or "esp32_001"

    scan = analytics_store.get_latest_scan(user_id=uid, zone_id=zid)
    sensor = sensor_store.get_latest(uid, zid, did)

    if scan:
        from services.plant_health import compute_from_scan_record

        return compute_from_scan_record(scan, sensor)

    if sensor:
        return compute_plant_health(
            "healthy",
            0.5,
            accepted=True,
            sensor=sensor,
            source="demo" if getattr(sensor, "is_demo", False) else "live",
        )

    return compute_plant_health(
        "healthy",
        0.0,
        accepted=False,
        sensor=None,
        source="baseline",
    )


# ---------------------------------------------------------------------------
# Phase 3 — sensor health endpoint
# ---------------------------------------------------------------------------


def _freshness(age: float | None) -> str:
    """Mirror ``analytics_store._freshness`` (live ≤30s, stale ≤300s, else offline)."""

    if age is None:
        return "offline"
    if age <= 30:
        return "live"
    if age <= 300:
        return "stale"
    return "offline"


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


@router.get("/health/sensor", response_model=SensorHealthResponse)
async def sensor_health(
    device_id: str | None = Query(
        default=None,
        description="Optional device slug. When omitted, reports all known devices.",
    ),
) -> SensorHealthResponse:
    """Sensor-pipeline health: per-device freshness + retry telemetry.

    Phase 3 hardening — gives the frontend (and ops) a single endpoint that
    answers four questions simultaneously:

    * Is Supabase reachable right now?
    * For each device, when did we last receive a reading and is it fresh?
    * How many DB retries have we had to do recently (and against which op)?
    * What's the last validation / repository error we observed?
    """

    pg_ok = await ping() if SETTINGS.use_postgres else False
    mode = deployment_mode()

    devices: list[SensorDeviceHealth] = []
    seen_slugs: set[str] = set()

    # ---- explicit device path (single-device probe) ----------------------
    if device_id:
        slug = device_id.strip()
        if slug:
            devices.append(await _device_health_for_slug(slug))
            seen_slugs.add(slug)

    # ---- all known devices ----------------------------------------------
    else:
        # 1) DB-known devices first (authoritative).
        if SETTINGS.use_postgres and pg_ok:
            try:
                rows = await devices_repo.list_devices()
                for row in rows:
                    slug = (row.get("slug") or "").strip()
                    if not slug or slug in seen_slugs:
                        continue
                    devices.append(await _device_health_for_slug(slug, db_row=row))
                    seen_slugs.add(slug)
            except Exception as exc:  # noqa: BLE001 — health endpoint must never crash
                log.warning("/health/sensor list_devices failed: %s", exc)

        # 2) Plus anything in the in-memory cache that the DB doesn't know about
        #    (covers memory-only mode + brand-new devices that haven't been
        #    upserted yet).
        for reading in sensor_store.list_all_readings():
            slug = reading.device_id
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            age = _age_seconds_iso(reading.timestamp)
            devices.append(
                SensorDeviceHealth(
                    device_id=slug,
                    zone_id=reading.zone_id,
                    user_id=reading.user_id,
                    freshness=_freshness(age),  # type: ignore[arg-type]
                    age_seconds=round(age, 2) if age is not None else None,
                    last_seen_at=reading.timestamp,
                    source="memory",
                    has_reading=True,
                )
            )

    # ---- overall status ---------------------------------------------------
    if not devices:
        overall = "offline"
    elif any(d.freshness == "live" for d in devices):
        overall = "healthy"
    elif any(d.freshness == "stale" for d in devices):
        overall = "degraded"
    else:
        overall = "offline"

    if SETTINGS.use_postgres and not pg_ok:
        overall = "degraded"

    # ---- retry telemetry --------------------------------------------------
    retry_stats = get_retry_stats()
    recent_events = get_recent_retry_events(limit=10)
    last_error = next(
        (e.get("message") for e in reversed(recent_events) if e.get("outcome") == "failed"),
        None,
    )

    # validation_failures_24h is fed from the dedicated in-process
    # counter that the RequestValidationError handler in main.py bumps
    # whenever /sensor receives a malformed payload. The durable record
    # of *which* payload failed lives in public.analytics_events
    # (event_type='sensor_validation_failed').
    failed_events_24h = count_validation_failures(within_seconds=86400.0)

    return SensorHealthResponse(
        status=overall,  # type: ignore[arg-type]
        persistence_backend=SETTINGS.persistence_backend,  # type: ignore[arg-type]
        deployment=mode,  # type: ignore[arg-type]
        postgres_reachable=pg_ok,
        devices=devices,
        retry_stats=retry_stats,
        recent_retry_events=recent_events,
        validation_failures_24h=failed_events_24h,
        last_error=last_error,
    )


@router.get("/health/audit")
async def health_audit(
    limit: int = Query(default=25, ge=1, le=200),
    event_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
) -> dict:
    """Phase 3 — recent audit trail (operator-facing).

    Returns the most recent rows from ``public.audit_log`` (DB-backed when
    Supabase is reachable; falls back to the in-process ring buffer when
    not). Useful for postmortems and the ops dashboard.
    """

    rows = await audit_log.list_recent(
        limit=limit, event_type=event_type, severity=severity
    )
    return {
        "count": len(rows),
        "filters": {"event_type": event_type, "severity": severity, "limit": limit},
        "events": rows,
    }


def _age_seconds_iso(iso_ts: str | None) -> float | None:
    if not iso_ts:
        return None
    try:
        return time.time() - datetime.fromisoformat(iso_ts.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


async def _device_health_for_slug(
    slug: str, db_row: dict | None = None
) -> SensorDeviceHealth:
    """Resolve freshness for a single device, preferring memory cache then DB."""

    # 1) memory cache (fastest, always wins when present).
    cached = next(
        (r for r in sensor_store.list_all_readings() if r.device_id == slug),
        None,
    )
    if cached is not None:
        age = _age_seconds_iso(cached.timestamp)
        return SensorDeviceHealth(
            device_id=slug,
            zone_id=cached.zone_id,
            user_id=cached.user_id,
            freshness=_freshness(age),  # type: ignore[arg-type]
            age_seconds=round(age, 2) if age is not None else None,
            last_seen_at=cached.timestamp,
            source="memory",
            has_reading=True,
        )

    # 2) DB-backed last reading.
    if SETTINGS.use_postgres:
        try:
            row = await sensor_repo.latest_for_device(slug)
        except Exception as exc:  # noqa: BLE001
            log.warning("latest_for_device(%s) failed in /health/sensor: %s", slug, exc)
            row = None
        if row:
            recorded_at = row.get("recorded_at")
            iso = _iso(recorded_at if isinstance(recorded_at, datetime) else None)
            age = _age_seconds_iso(iso) if iso else None
            return SensorDeviceHealth(
                device_id=slug,
                zone_id=row.get("zone_slug"),
                user_id=row.get("user_slug"),
                freshness=_freshness(age),  # type: ignore[arg-type]
                age_seconds=round(age, 2) if age is not None else None,
                last_seen_at=iso,
                source="postgres",
                has_reading=True,
            )

    # 3) device known but never reported a reading — surface 'offline'.
    zone_slug = (db_row or {}).get("zone_slug")
    last_seen_dt = (db_row or {}).get("last_seen")
    return SensorDeviceHealth(
        device_id=slug,
        zone_id=zone_slug,
        user_id=None,
        freshness="offline",
        age_seconds=None,
        last_seen_at=_iso(last_seen_dt) if isinstance(last_seen_dt, datetime) else None,
        source="none",
        has_reading=False,
    )
