"""Gemini contextual reasoning: diagnosis × environment × user question.

Builds a compact JSON context (diagnosis, every available sensor value with
its timestamp/age, the rule-based survival score, recent scans and the
user's question), optionally attaches the photo, and asks Gemini for a
validated ``GeminiReasoning`` answer. Never cached: the sensor context
changes over time.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from services.gemini.client import GeminiClient, get_gemini_client
from services.gemini.prompts import PROMPT_VERSION, reasoning_system, reasoning_user_prompt
from services.gemini.schemas import GeminiReasoning

SENSOR_FIELDS = (
    "air_temperature",
    "air_humidity",
    "soil_temperature",
    "soil_humidity",
    "soil_ph",
    "soil_ec",
    "light_lux",
)


@dataclass
class ReasoningOutcome:
    reasoning: GeminiReasoning
    model: str
    call: dict[str, Any]

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "google_gemini",
            "model": self.model,
            "prompt_version": PROMPT_VERSION,
            "call": self.call,
        }

    def reply_text(self) -> str:
        return self.reasoning.answer.strip() or self.reasoning.summary.strip()

    def primary_recommendation(self) -> str:
        for item in self.reasoning.urgent_actions + self.reasoning.recommendations:
            if item and item.strip():
                return item.strip()
        return self.reasoning.summary.strip()


def _age_seconds(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    try:
        return round(time.time() - datetime.fromisoformat(str(timestamp).replace("Z", "+00:00")).timestamp(), 1)
    except (TypeError, ValueError):
        return None


def build_sensor_context(values: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise sensor values; missing readings stay ``None`` (never invented)."""

    values = values or {}
    out: dict[str, Any] = {}
    for name in SENSOR_FIELDS:
        v = values.get(name)
        try:
            out[name] = None if v is None else float(v)
        except (TypeError, ValueError):
            out[name] = None
    ts = values.get("timestamp")
    out["timestamp"] = ts
    out["age_seconds"] = _age_seconds(ts)
    out["source"] = values.get("source") or ("device" if ts else "client")
    return out


def build_reasoning_context(
    *,
    diagnosis: dict[str, Any] | None,
    vision_summary: dict[str, Any] | None,
    sensors: dict[str, Any] | None,
    survival: dict[str, Any] | None,
    history: list[dict[str, Any]] | None,
    user_question: str | None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "diagnosis": diagnosis,
        "scan_summary": vision_summary,
        "sensors": build_sensor_context(sensors),
        "survival_score": survival,
        "user_question": (user_question or "").strip()
        or "Summarise this plant's condition and what I should do now.",
    }
    if history:
        ctx["recent_scans"] = history
    return ctx


def reason_about_plant(
    context: dict[str, Any],
    *,
    image: tuple[bytes, str] | None = None,
    language: str | None = None,
    client: GeminiClient | None = None,
) -> ReasoningOutcome:
    """Run the reasoning call. ``image`` is an optional ``(jpeg_bytes, mime)`` pair."""

    client = client or get_gemini_client()
    model = client.config.reasoning_model
    contents: list[Any] = []
    if image is not None:
        contents.append(client.image_part(image[0], image[1]))
    contents.append(reasoning_user_prompt(context))

    reasoning, info = client.generate_json(
        operation="reasoning",
        model=model,
        contents=contents,
        schema=GeminiReasoning,
        system_instruction=reasoning_system(language),
        temperature=client.config.reasoning_temperature,
    )
    return ReasoningOutcome(reasoning=reasoning, model=info.model, call=info.as_dict())
