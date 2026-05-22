"""
Phase 3 — Scan history endpoints.

The legacy `/analytics/history` returns the slim in-memory deque shape
(scan_id, disease, confidence, status, timestamp). These richer endpoints
read directly from `scan_results` so the frontend can render a full Scan
History dashboard with thumbnails, sensor snapshots, plant_id, etc.

Memory fallback: if Postgres is unavailable, the endpoints return the
in-memory analytics deque shape so the page still works in demo mode.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from db.connection import get_pool, is_postgres_enabled
from repositories import scans_repo
from services import analytics_store

log = logging.getLogger("plantvision.scans")

router = APIRouter(prefix="/scans", tags=["scans"])


# ---------------------------------------------------------------- schemas


class ScanListItem(BaseModel):
    id: str
    user_id: str | None = None
    zone_id: str | None = None
    device_id: str | None = None
    plant_id: str | None = None
    plant_name: str | None = None
    disease: str | None = None
    disease_type: str | None = None
    class_name: str | None = None
    confidence: float = 0.0
    accepted: bool = True
    status: str = "WARN"  # PASS / WARN / CRITICAL / UNKNOWN
    health_score: int | None = None
    risk_level: str | None = None
    environment_stress: str | None = None
    survival_score: int | None = None
    image_url: str | None = None
    image_path: str | None = None
    scan_source: str | None = None
    model_name: str | None = None
    created_at: str
    has_sensor_snapshot: bool = False
    is_legacy: bool = False  # row predates Phase 3 metadata enrichment


class ScanDetail(ScanListItem):
    recommendation: str | None = None
    metadata: dict[str, Any] = {}
    sensor_snapshot: dict[str, Any] | None = None


class ScanListResponse(BaseModel):
    source: str           # "postgres" | "memory" | "demo"
    total: int
    zone: str | None = None
    status_filter: str | None = None
    scans: list[ScanListItem]


class ZoneScanCounts(BaseModel):
    source: str
    counts: dict[str, int]
    by_status: dict[str, dict[str, int]] = {}


# ---------------------------------------------------------------- helpers


_HEALTHY = ("healthy", "normal", "no disease", "none")
_UNCLASSIFIED = {"", "unknown", "pending", "pending analysis", "unclassified", "n/a"}


def _status_from(disease: str | None, confidence: float, accepted: bool) -> str:
    """Status pill mapping.

    UNKNOWN is reserved for *truly unclassified* rows (empty / literal
    "Unknown" disease strings). A real prediction like "Diseased" with a
    modest 0.35 confidence is still a WARN — never demote a valid
    detection to UNKNOWN just because the confidence is low; that is what
    the confidence percentage itself is for.
    """
    d = (disease or "").strip().lower()
    if not d or d in _UNCLASSIFIED:
        return "UNKNOWN"
    if any(x in d for x in _HEALTHY):
        return "PASS"
    if confidence >= 0.9 or (not accepted and confidence >= 0.7):
        return "CRITICAL"
    return "WARN"


def _row_to_item(row: dict[str, Any]) -> ScanListItem:
    raw_meta = row.get("metadata_json") or {}
    meta: dict[str, Any]
    if isinstance(raw_meta, str):
        try:
            meta = json.loads(raw_meta)
        except (TypeError, ValueError):
            meta = {}
    elif isinstance(raw_meta, dict):
        meta = raw_meta
    else:
        meta = {}

    image_path = row.get("image_path") or meta.get("saved_path")
    image_url = meta.get("image_url") or (("/" + image_path) if image_path else None)
    # Normalise legacy Windows-style separators so the browser/static mount can serve them.
    if image_url:
        image_url = image_url.replace("\\", "/")
    if image_path:
        image_path = image_path.replace("\\", "/")
    created = row.get("created_at")
    created_iso = created.isoformat() if hasattr(created, "isoformat") else str(created or "")

    has_snap = isinstance(meta.get("sensor_snapshot"), dict)
    # A row is "legacy" if it lacks the Phase 3 metadata enrichment OR has a
    # placeholder/low-confidence disease label. UI uses this to show a clean
    # "Legacy scan" subtitle instead of poisoning the dashboard.
    disease_val = (row.get("disease") or "").strip()
    is_legacy = (
        not has_snap
        and not meta.get("plant_id")
        and not meta.get("scan_source")
    )

    return ScanListItem(
        id=str(row.get("id") or ""),
        user_id=row.get("user_slug") or meta.get("user_id"),
        zone_id=row.get("zone_slug"),
        device_id=row.get("device_slug") or meta.get("device_id"),
        plant_id=meta.get("plant_id"),
        plant_name=meta.get("plant_name"),
        disease=disease_val or None,
        disease_type=row.get("disease_type") or meta.get("disease_type"),
        class_name=row.get("prediction_class") or meta.get("class_name"),
        confidence=float(row.get("confidence") or 0.0),
        accepted=bool(row.get("accepted") if row.get("accepted") is not None else True),
        status=_status_from(
            row.get("disease"),
            float(row.get("confidence") or 0.0),
            bool(row.get("accepted") if row.get("accepted") is not None else True),
        ),
        health_score=row.get("health_score"),
        risk_level=row.get("risk_level"),
        environment_stress=meta.get("environment_stress"),
        survival_score=row.get("survival_score"),
        image_url=image_url,
        image_path=image_path,
        scan_source=meta.get("scan_source"),
        model_name=row.get("model_name"),
        created_at=created_iso,
        has_sensor_snapshot=has_snap,
        is_legacy=is_legacy,
    )


def _row_to_detail(row: dict[str, Any]) -> ScanDetail:
    base = _row_to_item(row).model_dump()
    raw_meta = row.get("metadata_json") or {}
    if isinstance(raw_meta, str):
        try:
            meta = json.loads(raw_meta)
        except (TypeError, ValueError):
            meta = {}
    elif isinstance(raw_meta, dict):
        meta = raw_meta
    else:
        meta = {}
    base["recommendation"] = row.get("recommendation")
    base["metadata"] = meta
    snap = meta.get("sensor_snapshot")
    base["sensor_snapshot"] = snap if isinstance(snap, dict) else None
    return ScanDetail(**base)


async def _list_from_db(
    zone: str | None,
    limit: int,
    status_filter: str | None,
) -> list[dict[str, Any]] | None:
    """Return raw rows from Postgres, or None when the pool is unavailable."""

    if not is_postgres_enabled():
        return None
    pool = await get_pool()
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            if zone:
                rows = await conn.fetch(
                    """
                    select * from public.scan_results
                    where zone_slug = $1
                    order by created_at desc
                    limit $2
                    """,
                    zone, limit,
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
            items = [dict(r) for r in rows]
            if status_filter:
                sf = status_filter.upper()
                items = [
                    r for r in items
                    if _status_from(
                        r.get("disease"),
                        float(r.get("confidence") or 0.0),
                        bool(r.get("accepted") if r.get("accepted") is not None else True),
                    ) == sf
                ]
            return items
    except Exception as exc:  # noqa: BLE001 — never let scan history crash the API
        log.warning("scans/_list_from_db failed: %s", exc)
        return None


def _memory_fallback(zone: str | None, limit: int, status_filter: str | None) -> list[ScanListItem]:
    """Best-effort: synthesise list items from the in-memory deque."""

    items: list[ScanListItem] = []
    for s in analytics_store._scans:  # type: ignore[attr-defined]  # private but stable
        zid = s.get("zone_id")
        if zone and zid != zone:
            continue
        st = s.get("status") or "WARN"
        if status_filter and st.upper() != status_filter.upper():
            continue
        ts = s.get("timestamp")
        try:
            from datetime import datetime, timezone
            created_iso = datetime.fromtimestamp(float(ts), tz=timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            created_iso = ""
        items.append(ScanListItem(
            id=str(s.get("scan_id") or ""),
            user_id=s.get("user_id"),
            zone_id=zid,
            device_id=None,
            disease=s.get("disease"),
            confidence=float(s.get("confidence") or 0.0),
            accepted=bool(s.get("accepted", True)),
            status=st,
            created_at=created_iso,
            has_sensor_snapshot=False,
        ))
        if len(items) >= limit:
            break
    return items


# ---------------------------------------------------------------- routes


@router.get("/history", response_model=ScanListResponse)
async def list_scans(
    zone: str | None = Query(default=None, description="Filter by zone slug (e.g. zone_alpha)"),
    status: str | None = Query(default=None, description="PASS | WARN | CRITICAL"),
    limit: int = Query(default=50, ge=1, le=200),
) -> ScanListResponse:
    """Rich scan history. DB-backed when possible, memory fallback otherwise."""

    rows = await _list_from_db(zone, limit, status)
    if rows is not None:
        items = [_row_to_item(r) for r in rows]
        return ScanListResponse(
            source="postgres", total=len(items), zone=zone, status_filter=status, scans=items,
        )
    items = _memory_fallback(zone, limit, status)
    if items:
        return ScanListResponse(
            source="memory", total=len(items), zone=zone, status_filter=status, scans=items,
        )
    return ScanListResponse(
        source="demo", total=0, zone=zone, status_filter=status, scans=[],
    )


@router.get("/zone-counts", response_model=ZoneScanCounts)
async def zone_counts() -> ZoneScanCounts:
    """Per-zone scan counts (and per-zone status breakdown) for Garden badges."""

    if is_postgres_enabled():
        pool = await get_pool()
        if pool is not None:
            try:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        select zone_slug, disease, confidence, accepted
                        from public.scan_results
                        where zone_slug is not null
                        """
                    )
                counts: dict[str, int] = {}
                by_status: dict[str, dict[str, int]] = {}
                for r in rows:
                    zid = r["zone_slug"]
                    counts[zid] = counts.get(zid, 0) + 1
                    st = _status_from(r["disease"], float(r["confidence"] or 0.0), bool(r["accepted"]))
                    bucket = by_status.setdefault(zid, {"PASS": 0, "WARN": 0, "CRITICAL": 0, "UNKNOWN": 0})
                    bucket[st] = bucket.get(st, 0) + 1
                return ZoneScanCounts(source="postgres", counts=counts, by_status=by_status)
            except Exception as exc:  # noqa: BLE001
                log.warning("zone_counts DB failed: %s", exc)

    # Memory fallback
    counts: dict[str, int] = {}
    by_status: dict[str, dict[str, int]] = {}
    for s in analytics_store._scans:  # type: ignore[attr-defined]
        zid = s.get("zone_id")
        if not zid:
            continue
        counts[zid] = counts.get(zid, 0) + 1
        st = (s.get("status") or "WARN").upper()
        bucket = by_status.setdefault(zid, {"PASS": 0, "WARN": 0, "CRITICAL": 0, "UNKNOWN": 0})
        bucket[st] = bucket.get(st, 0) + 1
    return ZoneScanCounts(source="memory", counts=counts, by_status=by_status)


# ---------------------------------------------------------------- Plant profile


class PlantProfile(BaseModel):
    plant_id: str
    plant_name: str | None = None
    plant_type: str | None = None
    current_zone: str | None = None
    scan_count: int = 0
    last_scanned_at: str | None = None
    latest_scan: ScanListItem | None = None
    recent_scans: list[ScanListItem] = []
    source: str = "demo"  # postgres | memory | demo


@router.get("/plant/{plant_id}", response_model=PlantProfile)
async def plant_profile(plant_id: str) -> PlantProfile:
    """Return a lightweight Plant Profile aggregated from scan_results.

    `plant_id` is matched against `metadata_json->>'plant_id'`. When the
    database is unavailable the endpoint falls back to memory + finally to
    an empty profile so the UI never breaks.
    """

    pid = (plant_id or "").strip()
    # Final polish — the MVP default plant is cucumber_001. Legacy scans
    # saved before the Phase 3 plant_id field was wired do NOT have
    # metadata.plant_id set, so a strict match would hide all history and
    # incorrectly show "Awaiting first scan". For the default plant_id we
    # fall back to all cucumber scans so the profile reflects real history.
    is_default = pid == "cucumber_001"

    # ---------- Postgres path -------------------------------------------------
    if is_postgres_enabled():
        pool = await get_pool()
        if pool is not None:
            try:
                async with pool.acquire() as conn:
                    rows = await conn.fetch(
                        """
                        select * from public.scan_results
                        where metadata_json->>'plant_id' = $1
                        order by created_at desc
                        limit 20
                        """,
                        pid,
                    )
                    items = [_row_to_item(dict(r)) for r in rows]
                    if not items and is_default:
                        rows = await conn.fetch(
                            """
                            select * from public.scan_results
                            order by created_at desc
                            limit 20
                            """,
                        )
                        items = [_row_to_item(dict(r)) for r in rows]
                    if items:
                        latest = items[0]
                        return PlantProfile(
                            plant_id=pid,
                            plant_name=next((i.plant_name for i in items if i.plant_name), None) or ("Cucumber" if is_default else None),
                            plant_type=next((i.disease_type for i in items if i.disease_type), None) or ("Cucumis sativus" if is_default else None),
                            current_zone=latest.zone_id,
                            scan_count=len(items),
                            last_scanned_at=latest.created_at,
                            latest_scan=latest,
                            recent_scans=items[:5],
                            source="postgres",
                        )
            except Exception as exc:  # noqa: BLE001
                log.warning("plant_profile DB failed: %s", exc)

    # ---------- Memory fallback ----------------------------------------------
    mem_items = []
    for s in analytics_store._scans:  # type: ignore[attr-defined]
        meta = (s.get("metadata") or {})
        if meta.get("plant_id") == pid or (is_default and not meta.get("plant_id")):
            mem_items.append(s)
    if mem_items:
        # Build minimal ScanListItem rows from in-memory shape.
        items: list[ScanListItem] = []
        for s in mem_items[:20]:
            items.append(
                ScanListItem(
                    id=str(s.get("scan_id") or s.get("id") or ""),
                    user_id=str(s.get("user_id") or "demo_user"),
                    zone_id=s.get("zone_id"),
                    device_id=s.get("device_id"),
                    plant_id=(s.get("metadata") or {}).get("plant_id") or (pid if is_default else None),
                    plant_name=(s.get("metadata") or {}).get("plant_name") or ("Cucumber" if is_default else None),
                    disease=s.get("disease") or s.get("class_name") or "",
                    disease_type=(s.get("metadata") or {}).get("disease_type"),
                    confidence=float(s.get("confidence") or 0.0),
                    health_score=(s.get("health") or {}).get("plant_health") if isinstance(s.get("health"), dict) else None,
                    image_url=(s.get("metadata") or {}).get("image_url"),
                    image_path=(s.get("metadata") or {}).get("saved_path"),
                    scan_source=s.get("source") or "upload",
                    status=_status_from(s.get("disease") or "", float(s.get("confidence") or 0.0), bool(s.get("accepted", True))),
                    created_at=str(s.get("timestamp") or s.get("created_at") or ""),
                )
            )
        latest = items[0] if items else None
        return PlantProfile(
            plant_id=pid,
            plant_name=("Cucumber" if is_default else None),
            plant_type=("Cucumis sativus" if is_default else None),
            scan_count=len(items),
            current_zone=(latest.zone_id if latest else None),
            last_scanned_at=(latest.created_at if latest else None),
            latest_scan=latest,
            recent_scans=items[:5],
            source="memory",
        )

    return PlantProfile(
        plant_id=pid,
        plant_name=("Cucumber" if is_default else None),
        plant_type=("Cucumis sativus" if is_default else None),
        source="demo",
    )


@router.get("/{scan_id}", response_model=ScanDetail)
async def scan_detail(scan_id: str) -> ScanDetail:
    """Full scan detail (incl. sensor snapshot) for the detail modal."""

    if is_postgres_enabled():
        pool = await get_pool()
        if pool is not None:
            try:
                async with pool.acquire() as conn:
                    row = await conn.fetchrow(
                        "select * from public.scan_results where id::text = $1 limit 1",
                        scan_id,
                    )
                    if row:
                        return _row_to_detail(dict(row))
            except Exception as exc:  # noqa: BLE001
                log.warning("scan_detail DB failed: %s", exc)
    raise HTTPException(status_code=404, detail=f"Scan {scan_id!r} not found")
