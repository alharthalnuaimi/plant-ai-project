from __future__ import annotations

import time
from typing import Any, Literal

from models.llama_model import (
    build_reasoning_prompts,
    fallback_narrative,
    parse_reasoning_response,
)
from schemas.contracts import OrchestratorRequest, OrchestratorResponse, SurvivalResponse
from services.model_manager import ModelManager
from services.prediction import run_vision_prediction
from services.survival import SurvivalInputs, compute_survival


def run_analysis_pipeline(
    *,
    request_id: str,
    image_bytes: bytes,
    request: OrchestratorRequest,
) -> OrchestratorResponse:
    t0 = time.perf_counter()
    warnings: list[str] = []

    t_vision_0 = time.perf_counter()
    vision = run_vision_prediction(image_bytes)
    t_vision = (time.perf_counter() - t_vision_0) * 1000.0
    if not vision.accepted:
        warnings.append(
            f"Vision confidence below threshold ({vision.confidence:.3f}); outputs may be unreliable."
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

    context: dict[str, Any] = {
        "vision": vision.model_dump(),
        "sensors": request.sensors.model_dump(),
        "survival": survival.model_dump(),
    }

    t_llm_0 = time.perf_counter()
    llm_source: Literal["ollama", "fallback", "fallback_empty_ollama", "fallback_error"] = "fallback"
    client = ModelManager.instance().get_llama_model()
    if client is None:
        explanation = fallback_narrative(
            {
                "vision": context["vision"],
                "sensors": context["sensors"],
                "survival_probability": survival.survival_probability,
            }
        )
        recommendation = "Increase watering consistency and reduce prolonged heat exposure."
        warnings.append("Ollama unavailable; used deterministic fallback narrative.")
    else:
        try:
            raw = client.generate_chat(build_reasoning_prompts(context, request.user_question))
            recommendation, explanation = parse_reasoning_response(raw, context)
            llm_source = "fallback_empty_ollama" if not raw else "ollama"
        except Exception:
            recommendation = "Increase watering consistency and reduce prolonged heat exposure."
            explanation = fallback_narrative(
                {
                    "vision": context["vision"],
                    "sensors": context["sensors"],
                    "survival_probability": survival.survival_probability,
                }
            )
            llm_source = "fallback_error"
            warnings.append("LLM call failed; fallback narrative was returned.")
    t_llm = (time.perf_counter() - t_llm_0) * 1000.0

    total_ms = (time.perf_counter() - t0) * 1000.0
    return OrchestratorResponse(
        request_id=request_id,
        vision=vision,
        survival=survival,
        recommendation=recommendation,
        llama_explanation=explanation,
        llm_source=llm_source,
        timings_ms={
            "vision_ms": round(t_vision, 2),
            "survival_ms": round(t_survival, 2),
            "llm_ms": round(t_llm, 2),
            "total_ms": round(total_ms, 2),
        },
        warnings=warnings,
    )

