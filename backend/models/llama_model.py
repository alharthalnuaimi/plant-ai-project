"""
Llama is used only for narrative: reasoning, recommendations, survival explanation.

Structured survival probability always comes from `services.survival` (rule-based MVP).
"""

from __future__ import annotations
from google import genai
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx
from services.prompt_loader import load_prompt


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

        prompt = "\n\n".join(
            f"{m['role'].upper()}:\n{m['content']}"
            for m in messages
        )

        client = genai.Client(api_key=self.api_key)

        response = client.models.generate_content(
            model=self.model,
            contents=prompt,
        )

        return response.text.strip()
    

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
    """Deterministic copy when Ollama is offline — keeps demos working."""
    sp = context.get("survival_probability")
    disease = (context.get("vision") or {}).get("disease")
    stress = (context.get("vision") or {}).get("stress_hint")
    sensors = context.get("sensors") or {}
    parts = []
    if sp is not None:
        parts.append(f"Estimated survival probability is about {float(sp) * 100:.0f}%.")
    if disease:
        parts.append(f"Vision suggests primary label: {disease}.")
    if stress:
        parts.append(f"Visual stress signal: {stress}.")
    if sensors:
        parts.append(f"Sensor snapshot: {json.dumps(sensors)}.")
    parts.append(
        "Increase watering if soil is dry; avoid prolonged heat; improve airflow if fungal disease is suspected. "
        "Confirm with a plant pathologist for production use."
    )
    return " ".join(parts)


def build_reasoning_prompts(context: dict[str, Any], user_question: str | None) -> list[dict[str, str]]:
    diagnosis = load_prompt("diagnosis")
    recovery = load_prompt("recovery")
    user_template = load_prompt("survival_analysis")
    system = "\n".join([x for x in [diagnosis, recovery] if x]).strip()
    if not system:
        system = (
            "Use only provided context. Do not invent disease labels. "
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
        print("CLEANED TEXT =")
        print(cleaned)
        data = json.loads(cleaned)
        print("PARSED JSON =", data)
        recommendation = str(data.get("recommendation", "")).strip()
        explanation = str(data.get("explanation", "")).strip()

        if recommendation and explanation:
            return recommendation, explanation

    except Exception as e:
        print("PARSE ERROR =", e)

    fb = fallback_narrative(fallback_context)
    return ("Increase watering consistency and reduce heat exposure.", fb)
