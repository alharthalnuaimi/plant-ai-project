from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SurvivalSensorInput(BaseModel):
    """Legacy survival/analyze sensor block (soil moisture + climate)."""

    soil_moisture: float = Field(ge=0, le=100, description="Soil moisture 0-100%")
    temperature: float = Field(description="Temperature in Celsius")
    humidity: float = Field(ge=0, le=100, description="Relative humidity 0-100%")
    species: str | None = Field(
        default=None,
        description="Optional species/cultivar; used for sensitivity scoring",
    )


# Backward-compatible alias for survival / analyze routes
SensorInput = SurvivalSensorInput


class VisionResult(BaseModel):
    disease: str
    confidence: float = Field(ge=0, le=1)
    stress_hint: str = ""
    model_name: str = "unknown"
    model_version: str = "unknown"
    accepted: bool = True
    inference_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SurvivalBreakdown(BaseModel):
    disease_component: float
    moisture_component: float
    temperature_component: float
    humidity_component: float
    species_component: float
    stress_component: float


class SurvivalResponse(BaseModel):
    survival_probability: float = Field(ge=0, le=1)
    breakdown: SurvivalBreakdown
    weights: dict[str, float]
    policy_version: str


class OrchestratorRequest(BaseModel):
    sensors: SurvivalSensorInput
    user_question: str | None = None
    persist_upload: bool = False


class OrchestratorResponse(BaseModel):
    request_id: str
    vision: VisionResult
    survival: SurvivalResponse
    recommendation: str
    llama_explanation: str
    llm_source: Literal["ollama", "fallback", "fallback_empty_ollama", "fallback_error"]
    timings_ms: dict[str, float]
    warnings: list[str] = Field(default_factory=list)

