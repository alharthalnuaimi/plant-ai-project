"""Care recommendation schemas (Phase 3)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Templates (raw config-driven plan)
# ---------------------------------------------------------------------------


class CareWatering(BaseModel):
    frequency: str | None = None
    soil_moisture_target: list[float] | None = Field(
        default=None, description="[min%, max%] target soil moisture range."
    )
    notes: str | None = None


class CareSunlight(BaseModel):
    lux_target: list[float] | None = Field(
        default=None, description="[min, max] lux range under canopy."
    )
    hours_per_day: list[float] | None = Field(
        default=None, description="[min, max] hours of direct/bright light per day."
    )
    notes: str | None = None


class CareSoil(BaseModel):
    ph_target: list[float] | None = None
    ec_target_ms: list[float] | None = Field(
        default=None, description="[min, max] EC in mS/cm."
    )
    type: str | None = None


class CareFertilizer(BaseModel):
    schedule: str | None = None
    npk: str | None = None
    notes: str | None = None


class GrowthStage(BaseModel):
    name: str
    duration_days: list[float] | None = None
    care_focus: str | None = None


class CareTemplate(BaseModel):
    """The static care blueprint loaded straight from configs/care_templates.yaml."""

    species_id: str
    common_name: str | None = None
    scientific_name: str | None = None
    family: str | None = None
    watering: CareWatering | None = None
    sunlight: CareSunlight | None = None
    temperature_c: list[float] | None = None
    humidity_pct: list[float] | None = None
    soil: CareSoil | None = None
    fertilizer: CareFertilizer | None = None
    growth_stages: list[GrowthStage] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Live recommendations (template + current sensor reading → actionable advice)
# ---------------------------------------------------------------------------


class CareRecommendation(BaseModel):
    """A single, actionable care item resolved against the latest sensor reading.

    ``severity`` ranks the urgency:
    * ``info``     — operational, no action needed
    * ``advice``   — preventive ("plant prefers higher humidity")
    * ``warning``  — out-of-band but tolerable
    * ``critical`` — actively harming the plant; act immediately
    """

    category: Literal[
        "watering", "sunlight", "temperature", "humidity", "soil_ph",
        "soil_ec", "fertilizer", "growth_stage", "general",
    ]
    severity: Literal["info", "advice", "warning", "critical"] = "info"
    message: str
    target: str | None = Field(default=None, description="Configured target range, human-readable.")
    current: str | None = Field(default=None, description="Latest observed value, human-readable.")


class CarePlan(BaseModel):
    """Resolved care plan returned by ``GET /care/{plant_id}``.

    Combines the static template (always present) with optional live
    recommendations + the inferred current growth stage. ``warnings`` is a
    flat list of severity ≥ warning items so the UI can render a banner
    without re-walking the recommendation tree.
    """

    species_id: str
    common_name: str | None = None
    scientific_name: str | None = None
    family: str | None = None
    template: CareTemplate
    recommendations: list[CareRecommendation] = Field(default_factory=list)
    warnings: list[CareRecommendation] = Field(default_factory=list)
    current_stage: GrowthStage | None = None
    has_sensor_context: bool = False
    source: Literal["config", "config+sensor"] = "config"
