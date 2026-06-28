"""
Llama / Gemini is used only for narrative: reasoning, recommendations, survival explanation.

Structured survival probability always comes from `services.survival` (rule-based MVP).
"""

from __future__ import annotations
from google import genai
import json
import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx
from services.prompt_loader import load_prompt


log = logging.getLogger("plantvision.llm")


@dataclass
class LlamaClient:
    base_url: str
    model: str
    timeout_s: float = 120.0

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        url = f"{self.base_url.rstrip('/')}/api/generate"
        payload = {
            "model": self.model,
            "prompt": f"{system_prompt}\n\n{user_prompt}",
            "stream": False,
        }
        with httpx.Client(timeout=self.timeout_s) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        return str(data.get("response", "")).strip()

    def generate_chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """Ollama /api/chat — preferred for instruction-tuned models."""
        url = f"{self.base_url.rstrip('/')}/api/chat"
        payload = {"model": self.model, "messages": messages, "stream": False}
        with httpx.Client(timeout=self.timeout_s) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        msg = data.get("message") or {}
        return str(msg.get("content", "")).strip()

@dataclass
class GeminiClient:
    api_key: str
    model: str

    def generate_chat(
        self,
        messages: list[dict[str, str]],
    ) -> str:
        """Send messages to Gemini using system_instruction + user content."""
        from google.genai import types as genai_types

        system_text = ""
        user_text = ""
        for m in messages:
            if m.get("role") == "system":
                system_text += m["content"] + "\n"
            else:
                user_text += m["content"] + "\n"

        client = genai.Client(api_key=self.api_key)

        config = genai_types.GenerateContentConfig(
            system_instruction=system_text.strip() if system_text.strip() else None,
        )

        response = client.models.generate_content(
            model=self.model,
            contents=user_text.strip(),
            config=config,
        )

        text = getattr(response, "text", None) or ""
        if not text and getattr(response, "candidates", None):
            try:
                parts = response.candidates[0].content.parts
                text = "".join(getattr(p, "text", "") or "" for p in parts)
            except (AttributeError, IndexError, TypeError):
                text = ""
        if not text.strip():
            log.warning("Gemini returned empty text for model=%s", self.model)
        return text.strip()
    

def get_llama_client() -> LlamaClient | None:
    base = os.getenv("OLLAMA_BASE_URL", "").strip()
    if not base:
        return None
    model = os.getenv("OLLAMA_MODEL", "llama3.1")
    return LlamaClient(base_url=base, model=model)

def get_gemini_client() -> GeminiClient | None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()

    if not api_key:
        return None

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    return GeminiClient(
        api_key=api_key,
        model=model,
    )

def fallback_narrative(context: dict[str, Any]) -> str:
    """Deterministic copy when the LLM (Gemini / Ollama) is offline.

    Prefixed with an honest disclaimer so the UI never implies the response
    came from the AI assistant when in fact it was rule-based.
    """

    sp = context.get("survival_probability")
    if sp is None:
        sp = (context.get("survival") or {}).get("survival_probability")
    vision = context.get("vision") or {}
    disease = vision.get("disease")
    stress = vision.get("stress_hint")
    plant = vision.get("plant") or {}
    sensors = context.get("sensors") or {}
    parts: list[str] = [
        "AI Plant Assistant is offline; here is a rule-based recommendation:",
    ]
    common_name = plant.get("common_name") if isinstance(plant, dict) else None
    if common_name:
        parts.append(f"Identified plant: {common_name}.")
    if sp is not None:
        try:
            parts.append(f"Estimated survival probability is about {float(sp) * 100:.0f}%.")
        except (TypeError, ValueError):
            pass
    if disease:
        parts.append(f"Vision suggests primary label: {disease}.")
    if stress:
        parts.append(f"Visual stress signal: {stress}.")
    if sensors:
        parts.append(f"Sensor snapshot: {json.dumps(sensors, ensure_ascii=True)}.")
    parts.append(
        "Increase watering if soil is dry; avoid prolonged heat; improve airflow if fungal disease is suspected. "
        "Confirm with a plant specialist before acting on production data."
    )
    return " ".join(parts)


# Removed fixed five-aspect structure — Gemini now answers the user's actual question naturally.


def build_reasoning_prompts(
    context: dict[str, Any],
    user_question: str | None,
) -> list[dict[str, str]]:
    """Build the (system, user) message pair for the reasoning LLM.

    ``context`` is expected to contain at least ``vision`` (a ``VisionResult``
    dump including the ``plant`` identification block) and ``sensors``.
    Optional keys: ``survival`` and ``history`` (a list of recent scan
    summaries — see ``routes.chat`` for how it is built).
    """

    diagnosis = load_prompt("diagnosis")
    recovery = load_prompt("recovery")
    user_template = load_prompt("survival_analysis")
    system_parts = [x for x in [diagnosis, recovery] if x]
    system = "\n".join(system_parts).strip()
    if not system:
        system = (
            "You are a knowledgeable plant care assistant. "
            "Answer the user's question directly. "
            "Return strict JSON with keys recommendation and explanation."
        )
    user = user_template.format(
        context_json=json.dumps(context, ensure_ascii=True),
        user_question=(user_question or ""),
    ) if user_template else f"Input JSON:\n{json.dumps({'context': context, 'user_question': user_question or ''}, ensure_ascii=True)}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def parse_reasoning_response(text: str, fallback_context: dict[str, Any]) -> tuple[str, str]:
    if not text:
        fb = fallback_narrative(fallback_context)
        return ("Monitor watering and heat stress closely.", fb)

    try:
        cleaned = text.strip()

        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]

        if cleaned.startswith("```"):
            cleaned = cleaned[3:]

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        cleaned = cleaned.strip()
        log.debug("LLM cleaned response: %s", cleaned)
        data = json.loads(cleaned)
        log.debug("LLM parsed JSON keys: %s", list(data.keys()) if isinstance(data, dict) else type(data).__name__)
        recommendation = str(data.get("recommendation", "")).strip()
        explanation = str(data.get("explanation", "")).strip()

        if recommendation and explanation:
            return recommendation, explanation

    except Exception as exc:  # noqa: BLE001 — never fail the route on parse error
        log.debug("LLM JSON parse error: %s", exc)

    fb = fallback_narrative(fallback_context)
    return ("Increase watering consistency and reduce heat exposure.", fb)
