"""Gemini multimodal plant diagnosis.

``diagnose_plant_image`` sends one compressed photo (plus an optional
species hint) to Gemini, validates the structured answer and applies the
consistency rules in ``schemas.enforce_diagnosis_consistency``.

The diagnosis is purely visual on purpose: environmental readings are
cross-referenced later by the reasoning step. That keeps a diagnosis
reusable for the same photo (cache) without ever mixing in old sensor
values.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

from services.gemini.cache import TTLCache
from services.gemini.client import GeminiClient, get_gemini_client
from services.gemini.config import GeminiConfig
from services.gemini.images import PreparedImage, prepare_image
from services.gemini.prompts import DIAGNOSIS_SYSTEM, PROMPT_VERSION, diagnosis_user_prompt
from services.gemini.schemas import GeminiDiagnosis, enforce_diagnosis_consistency

log = logging.getLogger("plantvision.gemini.diagnosis")


@dataclass
class DiagnosisOutcome:
    diagnosis: GeminiDiagnosis
    model: str
    prompt_version: str
    image: PreparedImage
    cached: bool
    call: dict[str, Any] | None = field(default=None)

    def metadata(self) -> dict[str, Any]:
        return {
            "provider": "google_gemini",
            "model": self.model,
            "prompt_version": self.prompt_version,
            "cached": self.cached,
            "image": self.image.describe(),
            "call": self.call,
            "confidence_kind": "model_self_reported",
        }


_cache_lock = threading.Lock()
_cache: TTLCache[GeminiDiagnosis] | None = None


def _get_cache(config: GeminiConfig) -> TTLCache[GeminiDiagnosis]:
    global _cache
    with _cache_lock:
        if (
            _cache is None
            or _cache.max_entries != config.cache_max_entries
            or _cache.ttl_s != config.cache_ttl_s
        ):
            _cache = TTLCache(config.cache_max_entries, config.cache_ttl_s)
        return _cache


def clear_diagnosis_cache() -> None:
    with _cache_lock:
        if _cache is not None:
            _cache.clear()


def _cache_key(image_hash: str, model: str, species_hint: str | None) -> str:
    hint = (species_hint or "").strip().lower()
    return f"{image_hash}|{model}|{PROMPT_VERSION}|{hint}"


def diagnose_plant_image(
    image_bytes: bytes,
    *,
    species_hint: str | None = None,
    client: GeminiClient | None = None,
) -> DiagnosisOutcome:
    """Diagnose one plant photo with Gemini. Raises a ``GeminiError`` / ``InvalidImageError`` on failure."""

    client = client or get_gemini_client()
    config = client.config
    model = config.diagnosis_model

    image = prepare_image(image_bytes, config)
    cache = _get_cache(config)
    key = _cache_key(image.sha256, model, species_hint)

    cached = cache.get(key)
    if cached is not None:
        log.info("gemini diagnosis cache hit model=%s", model)
        return DiagnosisOutcome(
            diagnosis=cached, model=model, prompt_version=PROMPT_VERSION, image=image, cached=True
        )

    raw, info = client.generate_json(
        operation="diagnosis",
        model=model,
        contents=[
            client.image_part(image.data, image.mime_type),
            diagnosis_user_prompt(species_hint),
        ],
        schema=GeminiDiagnosis,
        system_instruction=DIAGNOSIS_SYSTEM,
        temperature=config.diagnosis_temperature,
    )
    diagnosis = enforce_diagnosis_consistency(raw)
    cache.set(key, diagnosis)
    return DiagnosisOutcome(
        diagnosis=diagnosis,
        model=info.model,  # the model that answered, which is the fallback after a retry
        prompt_version=PROMPT_VERSION,
        image=image,
        cached=False,
        call=info.as_dict(),
    )


def primary_label(d: GeminiDiagnosis) -> str:
    """Human label used as the scan's ``raw_disease_label``."""

    status = d.diagnosis.status
    if status == "healthy":
        return "Healthy"
    if status == "not_assessable":
        return "Not assessable"
    if status == "uncertain" or not d.diagnosis.primary_condition:
        return "Uncertain"
    return d.diagnosis.primary_condition.strip()


_STRESS_HINTS = {
    "none": "no_strong_visual_stress_signal",
    "dehydration_or_sun_stress": "possible_dehydration_or_sun_stress",
    "yellowing_or_low_vigor": "low_vigor_or_yellowing",
    "other_stress": "other_visual_stress",
    "unknown": "unknown",
}


def stress_hint(d: GeminiDiagnosis) -> str:
    """Map onto the legacy ``stress_hint`` vocabulary read by ``services.survival``."""

    return _STRESS_HINTS.get(d.stress_signal, "unknown")


def user_guidance(d: GeminiDiagnosis) -> str | None:
    """A recommendation for diagnoses that cannot be acted on (bad photo / no plant / unclear)."""

    status = d.diagnosis.status
    if status == "not_assessable":
        note = (d.image_quality_notes or "").strip()
        if not d.plant_identification.is_plant:
            base = "No plant could be recognised in this photo."
        else:
            base = "The photo is not clear enough to assess the plant."
        return f"{base} {note} Retake the photo in good light, close to the affected leaves.".replace("  ", " ").strip()
    if status == "uncertain":
        return (
            "Symptoms are visible but the cause is not clear from this photo. "
            "Take a close-up of the affected leaves (top and underside) and scan again."
        )
    return None
