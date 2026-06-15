"""
Care recommendation engine (Phase 3).

Given a ``species_id`` and (optionally) the latest ``SensorReading``, this
module produces a ``CarePlan`` that combines:

1. The static care template (from ``configs/care_templates.yaml``).
2. Live recommendations comparing current sensor values to the template's
   target ranges (only when a sensor reading is available).
3. The inferred current growth stage (best-effort — uses days since the
   first persisted scan when scan history is provided; otherwise the first
   stage in the template).

The engine is **purely computational** — no DB calls, no IO, no logging
beyond the standard logger. That means it's trivial to unit-test (which we
do in Increment 5) and trivial to call from inside ``/predict`` and
``/report`` without making them slower.
"""

from __future__ import annotations

import logging
from typing import Any

from schemas.care import (
    CareFertilizer,
    CarePlan,
    CareRecommendation,
    CareSoil,
    CareSunlight,
    CareTemplate,
    CareWatering,
    GrowthStage,
)
from schemas.sensors import SensorReading
from services.config_loader import get_care_templates
from services.species_taxonomy import lookup as species_lookup

log = logging.getLogger("plantvision.care_engine")


# ---------------------------------------------------------------------------
# Template loading
# ---------------------------------------------------------------------------


def load_template(species_id: str | None) -> CareTemplate:
    """Resolve a ``CareTemplate`` for the given species_id.

    * Unknown species → falls back to cucumber (the MVP default).
    * Empty templates dict → returns a minimal template so the API
      contract still holds.
    """

    species = species_lookup(species_id)
    templates = get_care_templates()
    raw = templates.get(species.species_id) or {}

    return CareTemplate(
        species_id=species.species_id,
        common_name=species.common_name,
        scientific_name=species.scientific_name,
        family=species.family,
        watering=_parse_watering(raw.get("watering")),
        sunlight=_parse_sunlight(raw.get("sunlight")),
        temperature_c=_as_range(raw.get("temperature_c")),
        humidity_pct=_as_range(raw.get("humidity_pct")),
        soil=_parse_soil(raw.get("soil")),
        fertilizer=_parse_fertilizer(raw.get("fertilizer")),
        growth_stages=[
            GrowthStage(
                name=str(g.get("name", "")),
                duration_days=_as_range(g.get("duration_days")),
                care_focus=g.get("care_focus"),
            )
            for g in (raw.get("growth_stages") or [])
            if isinstance(g, dict)
        ],
    )


# ---------------------------------------------------------------------------
# Plan resolution
# ---------------------------------------------------------------------------


def build_care_plan(
    *,
    species_id: str | None,
    sensor: SensorReading | None = None,
    days_since_planted: int | None = None,
) -> CarePlan:
    """Assemble a ``CarePlan`` from template + (optional) live signals.

    Parameters
    ----------
    species_id : str | None
        Resolved via ``species_taxonomy.lookup`` — unknown slugs default to
        cucumber.
    sensor : SensorReading | None
        Latest sensor reading for the plant's zone/device. When supplied,
        the engine emits live recommendations and bumps ``source`` to
        ``"config+sensor"``.
    days_since_planted : int | None
        Used to pick a growth stage. When omitted, falls back to the first
        stage in the template.
    """

    template = load_template(species_id)

    recommendations: list[CareRecommendation] = []

    # --- Live, range-driven recommendations (only when sensor data exists) --
    if sensor is not None:
        recommendations.extend(_check_watering(template.watering, sensor))
        recommendations.extend(_check_sunlight(template.sunlight, sensor))
        recommendations.extend(_check_temperature(template.temperature_c, sensor))
        recommendations.extend(_check_humidity(template.humidity_pct, sensor))
        recommendations.extend(_check_soil(template.soil, sensor))

    # --- Static info chips so the UI always has something useful ----------
    recommendations.extend(_static_info(template))

    # --- Growth stage inference ------------------------------------------
    current_stage = _pick_stage(template, days_since_planted)

    warnings = [r for r in recommendations if r.severity in ("warning", "critical")]

    return CarePlan(
        species_id=template.species_id,
        common_name=template.common_name,
        scientific_name=template.scientific_name,
        family=template.family,
        template=template,
        recommendations=recommendations,
        warnings=warnings,
        current_stage=current_stage,
        has_sensor_context=sensor is not None,
        source="config+sensor" if sensor is not None else "config",
    )


# ---------------------------------------------------------------------------
# Live checks
# ---------------------------------------------------------------------------


def _check_range(
    *,
    category: Any,
    label: str,
    value: float | None,
    target: list[float] | None,
    unit: str = "",
    critical_factor: float = 1.5,
    advice_message: str | None = None,
    too_low_message: str | None = None,
    too_high_message: str | None = None,
) -> list[CareRecommendation]:
    """Generic range-vs-current emitter. One reusable function for all
    sensor-driven recommendations."""

    if target is None or len(target) != 2 or value is None:
        return []
    lo, hi = float(target[0]), float(target[1])
    span = max(hi - lo, 1e-6)
    target_str = f"{lo:g}-{hi:g}{unit}"
    current_str = f"{value:g}{unit}"

    if value < lo:
        gap = lo - value
        sev = "critical" if gap > span * (critical_factor - 1.0) else "warning"
        return [CareRecommendation(
            category=category,
            severity=sev,
            message=too_low_message or f"{label} below target ({current_str}, want {target_str})",
            target=target_str,
            current=current_str,
        )]
    if value > hi:
        gap = value - hi
        sev = "critical" if gap > span * (critical_factor - 1.0) else "warning"
        return [CareRecommendation(
            category=category,
            severity=sev,
            message=too_high_message or f"{label} above target ({current_str}, want {target_str})",
            target=target_str,
            current=current_str,
        )]
    return [CareRecommendation(
        category=category,
        severity="info",
        message=advice_message or f"{label} within target ({current_str}).",
        target=target_str,
        current=current_str,
    )]


def _check_watering(w: CareWatering | None, s: SensorReading) -> list[CareRecommendation]:
    if w is None:
        return []
    return _check_range(
        category="watering",
        label="Soil moisture",
        value=s.soil_humidity,
        target=w.soil_moisture_target,
        unit="%",
        too_low_message="Soil too dry — water now (within target range).",
        too_high_message="Soil too wet — pause watering and improve drainage.",
        advice_message="Soil moisture optimal; stick to the configured schedule.",
    )


def _check_sunlight(sl: CareSunlight | None, s: SensorReading) -> list[CareRecommendation]:
    if sl is None:
        return []
    return _check_range(
        category="sunlight",
        label="Light intensity",
        value=s.light_lux,
        target=sl.lux_target,
        unit=" lux",
        too_low_message="Light below preferred range — consider supplemental grow lights.",
        too_high_message="Light intensity exceeds preferred range — risk of leaf scorch.",
        advice_message="Light intensity within preferred range.",
    )


def _check_temperature(t: list[float] | None, s: SensorReading) -> list[CareRecommendation]:
    return _check_range(
        category="temperature",
        label="Air temperature",
        value=s.air_temperature,
        target=t,
        unit="°C",
        too_low_message="Air temperature below preferred range — risk of cold stress.",
        too_high_message="Air temperature above preferred range — increase ventilation.",
        advice_message="Air temperature within preferred range.",
    )


def _check_humidity(h: list[float] | None, s: SensorReading) -> list[CareRecommendation]:
    return _check_range(
        category="humidity",
        label="Air humidity",
        value=s.air_humidity,
        target=h,
        unit="%",
        too_low_message="Humidity low — consider misting or a humidifier.",
        too_high_message="Humidity high — improve airflow to deter fungal disease.",
        advice_message="Humidity within preferred range.",
    )


def _check_soil(soil: CareSoil | None, s: SensorReading) -> list[CareRecommendation]:
    if soil is None:
        return []
    out: list[CareRecommendation] = []
    out.extend(_check_range(
        category="soil_ph",
        label="Soil pH",
        value=s.soil_ph,
        target=soil.ph_target,
        too_low_message="Soil too acidic — apply a small amount of lime.",
        too_high_message="Soil too alkaline — top-dress with sulfur or compost.",
        advice_message="Soil pH within preferred range.",
    ))
    out.extend(_check_range(
        category="soil_ec",
        label="Soil EC",
        value=s.soil_ec,
        target=soil.ec_target_ms,
        unit=" mS/cm",
        too_low_message="Nutrient salts low — schedule fertilization.",
        too_high_message="Nutrient salts high — flush soil with plain water.",
        advice_message="Soil EC within preferred range.",
    ))
    return out


def _static_info(template: CareTemplate) -> list[CareRecommendation]:
    """Always-present informational chips so the UI has minimum content even
    without a sensor reading."""

    out: list[CareRecommendation] = []
    if template.watering and template.watering.frequency:
        out.append(CareRecommendation(
            category="watering",
            severity="info",
            message=f"Watering schedule: {template.watering.frequency}",
        ))
    if template.fertilizer and template.fertilizer.schedule:
        out.append(CareRecommendation(
            category="fertilizer",
            severity="info",
            message=f"Fertilizer schedule: {template.fertilizer.schedule}"
                    + (f" — NPK {template.fertilizer.npk}" if template.fertilizer.npk else ""),
        ))
    if template.soil and template.soil.type:
        out.append(CareRecommendation(
            category="soil_ph",
            severity="info",
            message=f"Preferred soil: {template.soil.type}",
        ))
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _as_range(raw: Any) -> list[float] | None:
    if not isinstance(raw, list) or len(raw) != 2:
        return None
    try:
        return [float(raw[0]), float(raw[1])]
    except (TypeError, ValueError):
        return None


def _parse_watering(raw: Any) -> CareWatering | None:
    if not isinstance(raw, dict):
        return None
    return CareWatering(
        frequency=raw.get("frequency"),
        soil_moisture_target=_as_range(raw.get("soil_moisture_target")),
        notes=raw.get("notes"),
    )


def _parse_sunlight(raw: Any) -> CareSunlight | None:
    if not isinstance(raw, dict):
        return None
    return CareSunlight(
        lux_target=_as_range(raw.get("lux_target")),
        hours_per_day=_as_range(raw.get("hours_per_day")),
        notes=raw.get("notes"),
    )


def _parse_soil(raw: Any) -> CareSoil | None:
    if not isinstance(raw, dict):
        return None
    return CareSoil(
        ph_target=_as_range(raw.get("ph_target")),
        ec_target_ms=_as_range(raw.get("ec_target_ms")),
        type=raw.get("type"),
    )


def _parse_fertilizer(raw: Any) -> CareFertilizer | None:
    if not isinstance(raw, dict):
        return None
    return CareFertilizer(
        schedule=raw.get("schedule"),
        npk=raw.get("npk"),
        notes=raw.get("notes"),
    )


def _pick_stage(template: CareTemplate, days_since_planted: int | None) -> GrowthStage | None:
    """Pick the active growth stage. Walks the stage list, accumulating the
    upper bound of each stage's duration; the first stage whose cumulative
    upper bound covers ``days_since_planted`` wins. When the input is
    ``None`` we just return the first stage so the UI has something to show.
    """

    if not template.growth_stages:
        return None
    if days_since_planted is None or days_since_planted < 0:
        return template.growth_stages[0]

    elapsed = float(days_since_planted)
    cumulative = 0.0
    for stage in template.growth_stages:
        upper = (stage.duration_days or [0, 0])[1]
        cumulative += float(upper or 0)
        if elapsed <= cumulative:
            return stage
    return template.growth_stages[-1]
