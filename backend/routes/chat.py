from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from models.llama_model import (
    build_reasoning_prompts,
    fallback_narrative,
    get_gemini_client,
    parse_reasoning_response,
)
from schemas.contracts import SurvivalSensorInput, SurvivalResponse, VisionResult
from services import analytics_store
from services.survival import SurvivalInputs, compute_survival

router = APIRouter(tags=["chat"])

log = logging.getLogger("plantvision.chat")


class ChatRequest(BaseModel):
    vision: VisionResult
    sensors: SurvivalSensorInput
    user_question: str | None = None


def _recent_scan_summaries(limit: int = 5) -> list[dict[str, Any]]:
    """Phase Final — Option A: enrich the LLM prompt with recent scans.

    We pull the newest ``limit`` rows from the in-memory scan history (which
    is hydrated from Postgres on startup) and reduce them to the smallest
    reasonable summary so the prompt stays compact. Returns ``[]`` on any
    error so /chat never breaks because of history enrichment.
    """

    try:
        rows = analytics_store.get_history(limit=limit)
    except Exception as exc:  # noqa: BLE001 — never block the chat route
        log.debug("scan history enrichment skipped: %s", exc)
        return []
    return [
        {
            "scan_id": r.scan_id,
            "zone_id": r.zone_id,
            "disease": r.disease,
            "confidence": round(float(r.confidence), 4),
            "status": r.status,
            "timestamp": r.timestamp,
        }
        for r in rows
    ]


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

    history = _recent_scan_summaries(limit=5)

    context: dict[str, Any] = {
        "vision": req.vision.model_dump(),
        "sensors": req.sensors.model_dump(),
        "survival": survival.model_dump(),
    }
    if history:
        context["history"] = history

    client = get_gemini_client()
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
            log.debug("Gemini raw response: %s", raw)
            recommendation, text = parse_reasoning_response(raw, context)
            if not raw:
                source = "fallback_empty_gemini"
            else:
                source = "gemini"
        except Exception as exc:  # noqa: BLE001 — never crash the chat route
            log.warning("Gemini call failed (%s) — using fallback narrative", exc)
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
