"""/analyze pipeline: Gemini diagnosis → rule-based survival score → Gemini reasoning.

Both AI steps call Google Gemini through ``services.gemini``. If either
fails, the structured ``GeminiError`` propagates to the client; there is
no Ollama call and no canned fallback narrative.
"""

from __future__ import annotations

import time
from typing import Any

from schemas.contracts import OrchestratorRequest, OrchestratorResponse, SurvivalResponse
from services.gemini.images import prepare_image
from services.gemini.reasoning import build_reasoning_context, reason_about_plant
from services.gemini.config import load_gemini_config
from services.prediction import run_vision_prediction
from services.survival import SurvivalInputs, compute_survival


def run_analysis_pipeline(
    *,
    request_id: str,
    image_bytes: bytes,
    request: OrchestratorRequest,
    language: str | None = None,
) -> OrchestratorResponse:
    t0 = time.perf_counter()
    warnings: list[str] = []

    t_vision_0 = time.perf_counter()
    vision = run_vision_prediction(image_bytes, language=language)
    t_vision = (time.perf_counter() - t_vision_0) * 1000.0
    if not vision.accepted:
        warnings.append(
            "Gemini could not give a confident diagnosis for this photo "
            f"(status: {vision.metadata.get('diagnosis_status', 'unknown')}); treat the results as provisional."
        )

    t_survival_0 = time.perf_counter()
    survival_dict = compute_survival(
        SurvivalInputs(
            disease=vision.disease,
            disease_confidence=vision.confidence,
            stress_hint=vision.stress_hint,
            soil_moisture=request.sensors.soil_moisture,
            temperature_c=request.sensors.temperature,
            humidity_pct=request.sensors.humidity,
            species=request.sensors.species,
        )
    )
    survival = SurvivalResponse.model_validate(survival_dict)
    t_survival = (time.perf_counter() - t_survival_0) * 1000.0

    sensors: dict[str, Any] = {
        "air_temperature": request.sensors.temperature,
        "air_humidity": request.sensors.humidity,
        "soil_humidity": request.sensors.soil_moisture,
        "source": "request",
    }
    context = build_reasoning_context(
        diagnosis=vision.metadata.get("gemini_diagnosis"),
        vision_summary={
            "label": vision.metadata.get("raw_disease_label", vision.disease),
            "confidence": vision.confidence if vision.metadata.get("confidence_available") else None,
            "accepted": vision.accepted,
            "species": request.sensors.species,
        },
        sensors=sensors,
        survival=survival.model_dump(),
        history=None,
        user_question=request.user_question,
    )

    # The reasoning step also sees the (compressed) photo, not just the findings.
    prepared = prepare_image(image_bytes, load_gemini_config())

    t_llm_0 = time.perf_counter()
    outcome = reason_about_plant(context, image=(prepared.data, prepared.mime_type), language=language)
    t_llm = (time.perf_counter() - t_llm_0) * 1000.0

    total_ms = (time.perf_counter() - t0) * 1000.0
    return OrchestratorResponse(
        request_id=request_id,
        vision=vision,
        survival=survival,
        recommendation=outcome.primary_recommendation(),
        llama_explanation=outcome.reply_text(),
        llm_source="gemini",
        reasoning=outcome.reasoning.model_dump(),
        timings_ms={
            "vision_ms": round(t_vision, 2),
            "survival_ms": round(t_survival, 2),
            "llm_ms": round(t_llm, 2),
            "total_ms": round(total_ms, 2),
        },
        warnings=warnings,
    )
