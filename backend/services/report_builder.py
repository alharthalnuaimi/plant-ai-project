"""
Unified AI Plant Report builder (Phase 3).

Synthesises five existing services into one canonical response:

1. ``services.prediction``        — disease detection + plant identification
2. ``services.plant_health``      — PlantHealthScore (rule-based)
3. ``services.care_engine``       — CarePlan (template + sensor-aware advice)
4. ``services.sensor_store``      — latest sensor reading per zone/device
5. ``services.analytics_store``   — last scan for the plant_id (for scientific
                                    identity + days-since-planted heuristic)

Two entry points:

* ``build_report_from_image()`` — full image-driven path used by the
  multipart variant of /report.
* ``build_report_from_plant_id()`` — JSON path that hydrates from the most
  recent persisted scan + sensor cache without re-running the vision model.

Both produce the same ``PlantReport`` schema.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from schemas.care import CareRecommendation
from schemas.contracts import PlantIdentification, VisionResult
from schemas.health import PlantHealthScore
from schemas.report import (
    PlantReport,
    ReportExplanation,
    ReportScores,
)
from schemas.sensors import SensorReading
from services import analytics_store, sensor_store
from services.care_engine import build_care_plan
from services.disease_taxonomy import classify_disease
from services.plant_health import compute_plant_health
from services.prediction import run_vision_prediction

log = logging.getLogger("plantvision.report")


# ---------------------------------------------------------------------------
# Score aggregation
# ---------------------------------------------------------------------------


_DISEASE_RISK_TO_PCT = {"Low": 15, "Medium": 45, "High": 72, "Critical": 92}
_STRESS_TO_PCT = {"Low": 12, "Medium": 45, "High": 78}


def _scores_from_health(health: PlantHealthScore) -> ReportScores:
    return ReportScores(
        plant_health=int(health.plant_health),
        disease_risk=int(_DISEASE_RISK_TO_PCT.get(health.disease_risk, 30)),
        stress_level=int(_STRESS_TO_PCT.get(health.environment_stress, 25)),
        survival_chance=int(health.survival_chance),
    )


def _explanation(
    *,
    health: PlantHealthScore,
    sensor: SensorReading | None,
    accepted: bool,
    confidence: float,
) -> ReportExplanation:
    """Build human-readable score narratives without invoking an LLM."""

    if health.class_name == "healthy":
        ph_msg = (
            f"Plant looks healthy ({health.plant_health}/100). "
            "Continue monitoring; no immediate action required."
        )
    else:
        ph_msg = (
            f"Plant health is {health.plant_health}/100 due to {health.disease_type or health.class_name} "
            "indicators in the image."
        )

    risk_lookup = {
        "Low": "Low — no concerning visual symptoms detected.",
        "Medium": "Medium — early signs of disease; act early to prevent spread.",
        "High": "High — clear disease indicators; isolate plant and treat immediately.",
        "Critical": "Critical — severe disease detected; remove affected tissue today.",
    }
    risk_msg = risk_lookup.get(health.disease_risk, "Medium — monitor closely.")
    if not accepted:
        risk_msg += f" (Detection confidence {confidence*100:.0f}% — re-scan recommended.)"

    if sensor is None:
        stress_msg = (
            "No live sensor reading available — environmental stress could not be evaluated."
        )
    else:
        stress_lookup = {
            "Low": "Environmental conditions are within target ranges.",
            "Medium": "One or more environmental readings are drifting from target — adjust within 24h.",
            "High": "Multiple environmental readings are out of range — environment is the primary stressor.",
        }
        stress_msg = stress_lookup.get(health.environment_stress, "Environment partially out of range.")

    if health.survival_chance >= 85:
        surv_msg = "Survival chance is excellent under current conditions."
    elif health.survival_chance >= 65:
        surv_msg = "Survival chance is good provided you act on the recommendations below."
    elif health.survival_chance >= 45:
        surv_msg = "Survival chance is moderate — fix the highest-severity warning first."
    else:
        surv_msg = "Survival chance is low — intervene now to prevent further decline."

    return ReportExplanation(
        plant_health=ph_msg,
        disease_risk=risk_msg,
        stress_level=stress_msg,
        survival_chance=surv_msg,
    )


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------


def _species_id_from_meta(meta: dict[str, Any]) -> str | None:
    ident = (meta or {}).get("plant_identification") or {}
    return ident.get("species_id")


def _species_from_plant_id_slug(plant_id: str | None) -> str | None:
    if not plant_id:
        return None
    head = plant_id.split("_", 1)[0].strip().lower()
    return head or None


def _days_since(ts: Any) -> int | None:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            now = datetime.now(timezone.utc).timestamp()
            return max(0, int((now - float(ts)) // 86400))
        if isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, (now - dt).days)
    except (TypeError, ValueError):
        return None
    return None


def _summarise(
    *,
    plant_name: str | None,
    disease: str,
    accepted: bool,
    health: PlantHealthScore,
    warnings: list[CareRecommendation],
) -> str:
    label = plant_name or "Plant"
    if health.class_name == "healthy" and not warnings:
        return (
            f"{label} looks healthy. Plant health {health.plant_health}/100, "
            f"survival chance {health.survival_chance}/100. No action required right now."
        )

    parts = [f"{label}: "]
    if health.class_name != "healthy":
        parts.append(f"{disease} suspected")
        if not accepted:
            parts.append(" (low-confidence detection)")
        parts.append(". ")
    if warnings:
        crit = [w for w in warnings if w.severity == "critical"]
        warn = [w for w in warnings if w.severity == "warning"]
        if crit:
            parts.append(f"{len(crit)} critical environmental issue(s)")
            if warn:
                parts.append(f" and {len(warn)} additional warning(s)")
            parts.append(". ")
        elif warn:
            parts.append(f"{len(warn)} environmental warning(s). ")
    parts.append(
        f"Plant health {health.plant_health}/100, survival chance {health.survival_chance}/100."
    )
    return "".join(parts)


def _freshness(ts: Any) -> str:
    if not ts:
        return "none"
    try:
        if isinstance(ts, (int, float)):
            age = time.time() - float(ts)
        elif isinstance(ts, str):
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            age = time.time() - dt.timestamp()
        else:
            return "none"
    except (TypeError, ValueError):
        return "none"
    if age <= 30:
        return "live"
    if age <= 300:
        return "stale"
    return "offline"


# ---------------------------------------------------------------------------
# Image-driven path
# ---------------------------------------------------------------------------


def build_report_from_image(
    image_bytes: bytes,
    *,
    user_id: str = "demo_user",
    zone_id: str = "zone_alpha",
    device_id: str = "esp32_001",
    plant_id: str | None = None,
    species_id: str | None = None,
    identify: bool = True,
) -> PlantReport:
    """Run the full report pipeline on a fresh image."""

    timings: dict[str, float] = {}

    t = time.perf_counter()
    vision: VisionResult = run_vision_prediction(
        image_bytes,
        identify=identify,
        species_id=species_id,
    )
    timings["vision_ms"] = round((time.perf_counter() - t) * 1000.0, 2)

    sensor = sensor_store.get_latest(user_id=user_id, zone_id=zone_id, device_id=device_id)

    raw_label = (vision.metadata or {}).get("raw_disease_label") or vision.disease
    health = compute_plant_health(
        raw_label,
        float(vision.confidence),
        accepted=vision.accepted,
        sensor=sensor,
        source="live" if sensor is not None else "baseline",
    )

    # Resolve species: explicit override > vision.plant > plant_id slug heuristic > cucumber.
    resolved_species = (
        species_id
        or (vision.plant.species_id if vision.plant else None)
        or _species_from_plant_id_slug(plant_id)
    )

    days_planted = _days_since(
        (analytics_store.get_latest_scan_for_plant(plant_id, user_id=user_id) or {}).get("timestamp")
    ) if plant_id else None

    t = time.perf_counter()
    care = build_care_plan(species_id=resolved_species, sensor=sensor, days_since_planted=days_planted)
    timings["care_ms"] = round((time.perf_counter() - t) * 1000.0, 2)

    return _assemble_report(
        plant_id=plant_id,
        user_id=user_id,
        zone_id=zone_id,
        device_id=device_id,
        vision=vision,
        sensor=sensor,
        health=health,
        care=care,
        timings=timings,
        species_override=species_id,
    )


# ---------------------------------------------------------------------------
# JSON / hydration path
# ---------------------------------------------------------------------------


def build_report_from_plant_id(
    *,
    plant_id: str | None,
    user_id: str = "demo_user",
    zone_id: str = "zone_alpha",
    device_id: str = "esp32_001",
    species_id: str | None = None,
) -> PlantReport:
    """Build a report from the latest persisted scan + sensor cache.

    No image required — useful for the AI assistant ("how is cucumber_001
    doing?") and for the dashboard's plant-profile auto-refresh.
    """

    timings: dict[str, float] = {}
    latest = analytics_store.get_latest_scan_for_plant(plant_id, user_id=user_id) or {}

    resolved_zone = (latest.get("zone_id") or zone_id or "zone_alpha")
    resolved_device = (latest.get("device_id") or device_id or "esp32_001")

    sensor = sensor_store.get_latest(
        user_id=user_id, zone_id=resolved_zone, device_id=resolved_device
    )

    # Reconstruct enough of a VisionResult-shaped object from the persisted scan.
    meta = latest.get("metadata") or {}
    raw_label = meta.get("raw_disease_label") or latest.get("disease") or "unknown"
    confidence = float(latest.get("confidence", 0.0) or 0.0)
    accepted = bool(latest.get("accepted", True))
    tax = classify_disease(raw_label)

    plant_block: PlantIdentification | None = None
    ident_meta = meta.get("plant_identification") or {}
    if ident_meta:
        plant_block = PlantIdentification(**{
            k: ident_meta.get(k)
            for k in (
                "species_id",
                "common_name",
                "scientific_name",
                "family",
                "genus",
                "confidence",
                "source",
            )
        })

    vision = VisionResult(
        user_id=user_id,
        zone_id=resolved_zone,
        disease=tax["display_label"],
        confidence=round(confidence, 4),
        stress_hint=meta.get("stress_hint", ""),
        class_name=tax["class_name"],
        disease_type=tax["disease_type"],
        model_name=str(meta.get("model_name", latest.get("model_name", "unknown"))),
        model_version=str(meta.get("model_version", latest.get("model_version", "unknown"))),
        accepted=accepted,
        inference_ms=float(meta.get("inference_ms", 0.0) or 0.0),
        plant=plant_block,
        metadata=meta,
    )

    health = compute_plant_health(
        raw_label,
        confidence,
        accepted=accepted,
        sensor=sensor,
        source="live" if sensor is not None else "baseline",
    )

    resolved_species = (
        species_id
        or (plant_block.species_id if plant_block else None)
        or _species_id_from_meta(meta)
        or _species_from_plant_id_slug(plant_id)
    )

    days_planted = _days_since(latest.get("timestamp"))

    t = time.perf_counter()
    care = build_care_plan(species_id=resolved_species, sensor=sensor, days_since_planted=days_planted)
    timings["care_ms"] = round((time.perf_counter() - t) * 1000.0, 2)

    return _assemble_report(
        plant_id=plant_id,
        user_id=user_id,
        zone_id=resolved_zone,
        device_id=resolved_device,
        vision=vision,
        sensor=sensor,
        health=health,
        care=care,
        timings=timings,
        species_override=species_id,
    )


# ---------------------------------------------------------------------------
# Shared assembly
# ---------------------------------------------------------------------------


def _assemble_report(
    *,
    plant_id: str | None,
    user_id: str,
    zone_id: str,
    device_id: str,
    vision: VisionResult,
    sensor: SensorReading | None,
    health: PlantHealthScore,
    care,
    timings: dict[str, float],
    species_override: str | None = None,
) -> PlantReport:
    plant_block = vision.plant
    plant_name = (
        (vision.metadata or {}).get("plant_name")
        or (plant_block.common_name if plant_block else None)
        or (care.common_name)
    )

    scores = _scores_from_health(health)
    explanation = _explanation(
        health=health,
        sensor=sensor,
        accepted=vision.accepted,
        confidence=float(vision.confidence),
    )
    summary = _summarise(
        plant_name=plant_name,
        disease=vision.disease,
        accepted=vision.accepted,
        health=health,
        warnings=care.warnings,
    )

    return PlantReport(
        plant_id=plant_id,
        user_id=user_id,
        zone_id=zone_id,
        device_id=device_id,
        plant_name=plant_name,
        scientific_name=(plant_block.scientific_name if plant_block else care.scientific_name),
        family=(plant_block.family if plant_block else care.family),
        plant=plant_block,
        disease=vision.disease,
        disease_class_name=vision.class_name,
        disease_type=vision.disease_type,
        confidence=float(vision.confidence),
        accepted=vision.accepted,
        model_name=vision.model_name,
        model_version=vision.model_version,
        scores=scores,
        explanation=explanation,
        health=health,
        sensor_data=sensor,
        sensor_freshness=_freshness(sensor.timestamp) if sensor else "none",
        care_recommendations=care.recommendations,
        warnings=care.warnings,
        care_plan=care,
        current_growth_stage=(care.current_stage.name if care.current_stage else None),
        analysis_summary=summary,
        timings_ms=timings,
        metadata={
            "species_resolution": "manual_override" if species_override else "auto",
        },
    )
