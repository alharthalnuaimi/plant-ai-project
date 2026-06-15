"""
Unified AI Plant Report (Phase 3) — schema for ``POST /report``.

This is the canonical synthesis endpoint: one image (or one plant_id) in,
one structured plant report out, combining vision + plant ID + sensor +
care plan + survival + scoring.

Design priorities:
* **Stable on missing inputs** — every nested block is optional. A request
  without a sensor reading still returns a usable report.
* **No new persistence** — the report stitches existing services; it does
  not introduce a new table.
* **Backwards-compatible with the legacy /predict shape** — the
  ``disease``, ``confidence`` and ``health.*`` fields are still exposed
  at the top level so older clients keep working unchanged.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.care import CarePlan, CareRecommendation
from schemas.contracts import PlantIdentification
from schemas.health import PlantHealthScore
from schemas.sensors import SensorReading


class ReportScores(BaseModel):
    """The four headline scores rendered in the unified report card."""

    plant_health: int = Field(ge=0, le=100)
    disease_risk: int = Field(ge=0, le=100, description="0=no risk, 100=critical")
    stress_level: int = Field(ge=0, le=100, description="0=optimal env, 100=severe stress")
    survival_chance: int = Field(ge=0, le=100)


class ReportExplanation(BaseModel):
    """Human-readable narrative for each score (no LLM required — these are
    rule-based summaries that the assistant can paraphrase later)."""

    plant_health: str = ""
    disease_risk: str = ""
    stress_level: str = ""
    survival_chance: str = ""


class PlantReport(BaseModel):
    """Unified plant report response.

    Fields are *additive on top of* the legacy /predict shape so the
    existing frontend continues working while new clients can read the
    richer ``plant`` / ``care`` / ``scores`` blocks.
    """

    # ---- Identity ---------------------------------------------------------
    plant_id: str | None = Field(default=None, description="Stable plant slug, e.g. 'cucumber_001'.")
    user_id: str = "demo_user"
    zone_id: str = "zone_alpha"
    device_id: str = "esp32_001"

    plant_name: str | None = Field(default=None, description="Display-friendly common name (mirrors plant.common_name).")
    scientific_name: str | None = None
    family: str | None = None
    plant: PlantIdentification | None = None

    # ---- Disease detection -----------------------------------------------
    disease: str = ""
    disease_class_name: str = Field(default="", description="Normalised disease slug.")
    disease_type: str = "unknown"
    confidence: float = Field(default=0.0, ge=0, le=1)
    accepted: bool = True
    model_name: str = "unknown"
    model_version: str = "unknown"

    # ---- Scores ----------------------------------------------------------
    scores: ReportScores
    explanation: ReportExplanation
    health: PlantHealthScore | None = None  # full PlantHealthScore for legacy clients

    # ---- Sensor context --------------------------------------------------
    sensor_data: SensorReading | None = None
    sensor_freshness: Literal["live", "stale", "offline", "none"] = "none"

    # ---- Care --------------------------------------------------------------
    care_recommendations: list[CareRecommendation] = Field(default_factory=list)
    warnings: list[CareRecommendation] = Field(default_factory=list)
    care_plan: CarePlan | None = None
    current_growth_stage: str | None = None

    # ---- Narrative -------------------------------------------------------
    analysis_summary: str = ""

    # ---- Diagnostics -----------------------------------------------------
    timings_ms: dict[str, float] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReportRequest(BaseModel):
    """Body for the JSON variant of /report (no image upload).

    Use this when the client wants a report on an already-scanned plant —
    we hydrate from the latest scan + sensor cache.
    """

    plant_id: str | None = None
    user_id: str = "demo_user"
    zone_id: str = "zone_alpha"
    device_id: str = "esp32_001"
    species_id: str | None = None
