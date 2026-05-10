from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from models.llama_model import (
    build_reasoning_prompts,
    fallback_narrative,
    get_llama_client,
    parse_reasoning_response,
)
from schemas.contracts import SensorInput, SurvivalResponse, VisionResult
from services.survival import SurvivalInputs, compute_survival

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    vision: VisionResult
    sensors: SensorInput
    user_question: str | None = None


@router.post("/chat")
async def chat(req: ChatRequest) -> dict:
    inp = SurvivalInputs(
        disease=req.vision.disease,
        disease_confidence=req.vision.confidence,
        stress_hint=req.vision.stress_hint,
        soil_moisture=req.sensors.soil_moisture,
        temperature_c=req.sensors.temperature,
        humidity_pct=req.sensors.humidity,
        species=req.sensors.species,
    )
    survival = SurvivalResponse.model_validate(compute_survival(inp))

    context = {
        "vision": req.vision.model_dump(),
        "sensors": req.sensors.model_dump(),
        "survival": survival.model_dump(),
    }

    client = get_llama_client()
    if client is None:
        recommendation = "Increase watering consistency and reduce prolonged heat exposure."
        text = fallback_narrative(
            {
                "vision": context["vision"],
                "sensors": context["sensors"],
                "survival_probability": survival.survival_probability,
            }
        )
        source = "fallback"
    else:
        try:
            raw = client.generate_chat(build_reasoning_prompts(context, req.user_question))
            recommendation, text = parse_reasoning_response(raw, context)
            if not raw:
                source = "fallback_empty_ollama"
            else:
                source = "ollama"
        except Exception:
            recommendation = "Increase watering consistency and reduce prolonged heat exposure."
            text = fallback_narrative(context)
            source = "fallback_error"

    return {
        "recommendation": recommendation,
        "reply": text,
        "source": source,
        "survival_probability": survival.survival_probability,
        "breakdown": survival.breakdown.model_dump(),
    }
