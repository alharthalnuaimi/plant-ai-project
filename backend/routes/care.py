"""
Plant care recommendation routes (Phase 3).

Endpoints
---------
* ``GET /care/species/{species_id}`` — pure config lookup (no sensor data
  required). Useful for the UI to show a static plan before any scan or
  sensor reading exists.
* ``GET /care/{plant_id}`` — resolves the plant via ``/scans/plant/{id}``
  semantics: looks up the latest scan + zone, finds the freshest sensor
  reading for that zone/device, and returns a ``CarePlan`` enriched with
  live recommendations and (best-effort) growth-stage inference.
* ``GET /care/`` — list all species_ids with templates.

These routes never crash on missing data: when no sensor reading is
available the ``has_sensor_context=false`` flag is set and the static
template still renders.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query

from schemas.care import CarePlan, CareTemplate
from services import analytics_store, sensor_store
from services.care_engine import build_care_plan, load_template
from services.config_loader import get_care_templates

log = logging.getLogger("plantvision.care")

router = APIRouter(prefix="/care", tags=["care"])


@router.get("", response_model=dict)
async def list_care_species() -> dict[str, Any]:
    """List all species_ids that have a care template configured."""

    templates = get_care_templates()
    return {
        "count": len(templates),
        "species_ids": sorted(templates.keys()),
    }


@router.get("/species/{species_id}", response_model=CareTemplate)
async def get_species_template(species_id: str) -> CareTemplate:
    """Return the static care template for a species.

    Unknown ``species_id`` falls back to the cucumber default so the
    endpoint never 404s — clients can compare ``response.species_id`` to
    the request to detect fallback.
    """

    return load_template(species_id)


@router.get("/{plant_id}", response_model=CarePlan)
async def get_plant_care(
    plant_id: str,
    user_id: str = Query(default="demo_user"),
    zone_id: str | None = Query(
        default=None,
        description="Override zone for sensor lookup. Defaults to the latest scan's zone.",
    ),
    device_id: str | None = Query(
        default=None,
        description="Override device for sensor lookup. Defaults to esp32_001.",
    ),
    species_id: str | None = Query(
        default=None,
        description="Override species. Defaults to the species recorded with the latest scan.",
    ),
) -> CarePlan:
    """Build a live care plan for ``plant_id``.

    Resolution order:

    1. ``species_id`` query override → wins.
    2. Else read ``species_id`` from the latest scan's
       ``metadata.plant_identification`` block.
    3. Else infer from ``plant_id`` slug (e.g. ``cucumber_001`` → cucumber).
    4. Else fall back to cucumber.
    """

    pid = (plant_id or "").strip()

    resolved_species = species_id
    resolved_zone = zone_id
    days_planted: int | None = None

    if not resolved_species or not resolved_zone:
        latest = analytics_store.get_latest_scan_for_plant(plant_id=pid, user_id=user_id)
        if latest is not None:
            meta = latest.get("metadata") or {}
            ident = (meta or {}).get("plant_identification") or {}
            if not resolved_species:
                resolved_species = ident.get("species_id") or _species_from_plant_id(pid)
            if not resolved_zone:
                resolved_zone = latest.get("zone_id") or "zone_alpha"
            ts = latest.get("timestamp") or latest.get("created_at")
            days_planted = _days_since(ts)

    if not resolved_species:
        resolved_species = _species_from_plant_id(pid)
    if not resolved_zone:
        resolved_zone = "zone_alpha"

    did = (device_id or "esp32_001").strip() or "esp32_001"

    # Best-effort sensor read — engine handles None.
    sensor = sensor_store.get_latest(user_id=user_id, zone_id=resolved_zone, device_id=did)

    return build_care_plan(
        species_id=resolved_species,
        sensor=sensor,
        days_since_planted=days_planted,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _species_from_plant_id(plant_id: str) -> str | None:
    """Last-ditch heuristic: infer species_id from a slug like ``cucumber_001``."""

    if not plant_id:
        return None
    head = plant_id.split("_", 1)[0].strip().lower()
    return head or None


def _days_since(ts: Any) -> int | None:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            seconds = float(ts)
            now = datetime.now(timezone.utc).timestamp()
            return max(0, int((now - seconds) // 86400))
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, (now - dt).days)
    except (TypeError, ValueError):
        return None
    return None
