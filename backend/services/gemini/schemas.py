"""Structured output contracts for Gemini diagnosis and reasoning.

These models do two jobs:

1. They are sent to Gemini as ``response_schema`` so the model is
   constrained to emit JSON of this shape.
2. Every response is validated against them again on our side
   (``model_validate_json``) before it reaches a route. A response that
   does not validate is rejected — it is never patched up with made-up
   values.

No field has a default value: Gemini's schema support rejects defaults,
and "required but nullable" keeps the model honest about what it does not
know (``null`` instead of a guess).

Confidence fields are the model's own self-assessment on a 0..1 scale.
They are not calibrated, measured probabilities, and the API labels them
that way (``confidence_kind = "model_self_reported"``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = float

# --------------------------------------------------------------------------
# Diagnosis (vision)
# --------------------------------------------------------------------------

ImageQuality = Literal["good", "acceptable", "poor", "unusable"]
DiagnosisStatus = Literal["healthy", "diseased", "stressed", "uncertain", "not_assessable"]
ConditionCategory = Literal[
    "fungal",
    "bacterial",
    "viral",
    "pest",
    "nutrient_deficiency",
    "environmental_stress",
    "physical_damage",
    "healthy",
    "unknown",
]
Severity = Literal["none", "mild", "moderate", "severe", "unknown"]
ObservationCategory = Literal[
    "discoloration",
    "spots_lesions",
    "fungal_sign",
    "bacterial_sign",
    "pest_damage",
    "nutrient_deficiency",
    "environmental_stress",
    "wilting",
    "physical_damage",
    "healthy_tissue",
    "other",
]
StressSignal = Literal[
    "none",
    "dehydration_or_sun_stress",
    "yellowing_or_low_vigor",
    "other_stress",
    "unknown",
]


class PlantIdentificationOut(BaseModel):
    is_plant: bool = Field(description="True only if a real plant is clearly visible in the image.")
    common_name: str | None = Field(description="Common species name, or null if not identifiable.")
    scientific_name: str | None = Field(description="Binomial name, or null if not identifiable.")
    family: str | None = Field(description="Botanical family, or null if unknown.")
    genus: str | None = Field(description="Botanical genus, or null if unknown.")
    confidence: Confidence | None = Field(
        ge=0, le=1, description="Self-assessed certainty of the identification, 0..1. Null if not identified."
    )


class DiagnosisOut(BaseModel):
    status: DiagnosisStatus = Field(
        description=(
            "healthy | diseased | stressed (abiotic stress, no disease) | "
            "uncertain (symptoms seen but cause unclear) | not_assessable (no plant or unusable image)."
        )
    )
    primary_condition: str | None = Field(
        description="Most likely disease or disorder name, e.g. 'Powdery Mildew'. Null unless status is diseased or stressed."
    )
    category: ConditionCategory
    confidence: Confidence | None = Field(
        ge=0, le=1, description="Self-assessed certainty of the primary condition, 0..1. Null when not assessable."
    )
    severity: Severity


class Observation(BaseModel):
    finding: str = Field(description="What is visible, described concretely (location, colour, pattern).")
    category: ObservationCategory
    certainty: Literal["confirmed", "possible"] = Field(
        description="confirmed = clearly visible in the image; possible = suggestive but not certain."
    )


class AlternativeDiagnosis(BaseModel):
    condition: str
    confidence: Confidence | None = Field(ge=0, le=1)
    reason: str = Field(description="Why this remains possible.")


class GeminiDiagnosis(BaseModel):
    image_quality: ImageQuality
    image_quality_notes: str | None = Field(description="Why the image is poor/unusable, else null.")
    plant_identification: PlantIdentificationOut
    diagnosis: DiagnosisOut
    observations: list[Observation]
    alternative_diagnoses: list[AlternativeDiagnosis]
    uncertainties: list[str] = Field(description="What cannot be determined from this image, and why.")
    stress_signal: StressSignal
    summary: str = Field(description="One or two plain sentences summarising the visual assessment.")


# --------------------------------------------------------------------------
# Reasoning (text)
# --------------------------------------------------------------------------

Urgency = Literal["low", "moderate", "high", "critical"]


class EnvironmentalAnalysis(BaseModel):
    temperature: str = Field(description="Assessment of air/soil temperature, or 'No data' if missing.")
    humidity: str = Field(description="Assessment of air humidity, or 'No data' if missing.")
    soil_conditions: str = Field(description="Soil moisture, pH and EC assessment, or 'No data' if missing.")
    light_conditions: str = Field(description="Light intensity assessment, or 'No data' if missing.")


class RecoveryAssessment(BaseModel):
    estimate: Literal["good", "fair", "poor"] | None = Field(
        description="Qualitative recovery outlook. Null when the evidence is not sufficient to judge."
    )
    confidence: Literal["low", "medium", "high"]
    explanation: str


class GeminiReasoning(BaseModel):
    answer: str = Field(description="Direct, conversational answer to the user's question.")
    summary: str
    disease_explanation: str
    possible_causes: list[str]
    environmental_analysis: EnvironmentalAnalysis
    recommendations: list[str]
    treatment_plan: list[str]
    prevention: list[str]
    urgent_actions: list[str] = Field(description="Actions needed within 24-48 hours; empty if none.")
    urgency: Urgency
    recovery_assessment: RecoveryAssessment


# --------------------------------------------------------------------------
# Post-validation consistency rules
# --------------------------------------------------------------------------


def enforce_diagnosis_consistency(d: GeminiDiagnosis) -> GeminiDiagnosis:
    """Strip any diagnosis the evidence cannot support.

    Applied after schema validation. It only ever *removes* claims (sets
    them to null / not_assessable); it never adds or invents values.
    """

    dx = d.diagnosis
    plant = d.plant_identification
    updates: dict = {}

    if d.image_quality == "unusable" or not plant.is_plant:
        dx = dx.model_copy(
            update={
                "status": "not_assessable",
                "primary_condition": None,
                "category": "unknown",
                "confidence": None,
                "severity": "unknown",
            }
        )
        updates["alternative_diagnoses"] = []
        if not plant.is_plant:
            updates["plant_identification"] = plant.model_copy(
                update={
                    "common_name": None,
                    "scientific_name": None,
                    "family": None,
                    "genus": None,
                    "confidence": None,
                }
            )
    elif dx.status in ("uncertain", "not_assessable"):
        dx = dx.model_copy(update={"primary_condition": None})
    elif dx.status in ("diseased", "stressed") and not (dx.primary_condition or "").strip():
        dx = dx.model_copy(update={"status": "uncertain", "primary_condition": None})

    if dx is not d.diagnosis:
        updates["diagnosis"] = dx
    return d.model_copy(update=updates) if updates else d
