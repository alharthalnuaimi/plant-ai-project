"""Image → ``VisionResult`` via Gemini multimodal diagnosis.

This is the single image-analysis entry point used by ``/predict``,
``/analyze`` and ``/report``. It calls only the Gemini service; the legacy
local pipeline (YOLO ``SpeciesAwareVisionPredictor``, the random-label
``StubVisionPredictor``, the Pl@ntNet / stub plant identifiers and the
multi-provider consensus) is kept in ``models/`` for reference but is no
longer reachable from here.

The response keeps the existing ``VisionResult`` contract so the frontend,
persistence and survival scoring work unchanged. The full structured
Gemini assessment is attached under ``metadata["gemini_diagnosis"]``.
"""

from __future__ import annotations

import logging
import time

from schemas.contracts import PlantIdentification, VisionResult
from services.config_loader import get_runtime_config
from services.disease_taxonomy import classify_disease
from services.gemini.diagnosis import (
    DiagnosisOutcome,
    diagnose_plant_image,
    primary_label,
    stress_hint,
    user_guidance,
)
from services.gemini.schemas import GeminiDiagnosis
from services.species_taxonomy import lookup as species_lookup

log = logging.getLogger("plantvision.prediction")

MODEL_NAME = "gemini"


def _threshold() -> float:
    return float(
        get_runtime_config()
        .get("thresholds", {})
        .get("prediction", {})
        .get("confidence_accept_threshold", 0.25)
    )


def _resolve_species_id(scientific_name: str | None, common_name: str | None) -> str:
    """Map a Gemini species name onto the local care catalog (``unknown`` if absent)."""

    for name in (scientific_name, common_name):
        if not name:
            continue
        key = name.lower().strip().replace(" ", "_")
        species_id = species_lookup(key).species_id
        if species_id == "unknown":
            species_id = species_lookup(key.split("_")[0]).species_id
        if species_id != "unknown":
            return species_id
    return "unknown"


def _manual_plant(species_id: str) -> PlantIdentification:
    entry = species_lookup(species_id)
    return PlantIdentification(
        species_id=entry.species_id,
        common_name=entry.common_name,
        scientific_name=entry.scientific_name,
        family=entry.family,
        # user-asserted identity is ground truth, unless we don't know that species
        confidence=0.0 if entry.species_id == "unknown" else 1.0,
        source="manual",
    )


def _gemini_plant(d: GeminiDiagnosis) -> PlantIdentification | None:
    p = d.plant_identification
    if not p.is_plant or not (p.common_name or p.scientific_name):
        return None
    return PlantIdentification(
        species_id=_resolve_species_id(p.scientific_name, p.common_name),
        common_name=p.common_name or p.scientific_name,
        scientific_name=p.scientific_name,
        family=p.family,
        genus=p.genus,
        confidence=p.confidence,
        source="gemini",
    )


def vision_result_from_diagnosis(
    outcome: DiagnosisOutcome,
    *,
    identify: bool,
    species_id: str | None,
    elapsed_ms: float,
) -> VisionResult:
    d = outcome.diagnosis
    label = primary_label(d)
    tax = classify_disease(label)
    # The local catalog lists only a few classes, so keep Gemini's own name for
    # any real condition it doesn't cover instead of storing "Unknown".
    disease = tax["display_label"]
    if tax["class_name"] == "unknown" and d.diagnosis.status in ("diseased", "stressed"):
        disease = label
    threshold = _threshold()

    confidence = d.diagnosis.confidence
    assessable = d.diagnosis.status not in ("uncertain", "not_assessable")
    accepted = bool(assessable and confidence is not None and confidence >= threshold)

    if species_id and species_id.strip():
        plant = _manual_plant(species_id)
    elif identify:
        plant = _gemini_plant(d)
    else:
        plant = None

    meta = {
        "threshold": threshold,
        "raw_disease_label": label,
        "diagnosis_status": d.diagnosis.status,
        "confidence_available": confidence is not None,
        "confidence_kind": "model_self_reported",
        "gemini_diagnosis": d.model_dump(),
        "gemini": outcome.metadata(),
        "image_size": list(outcome.image.original_size),
    }
    guidance = user_guidance(d)
    if guidance:
        meta["guidance"] = guidance

    return VisionResult(
        disease=disease,
        confidence=round(float(confidence or 0.0), 4),
        stress_hint=stress_hint(d),
        class_name=tax["class_name"],
        disease_type=tax["disease_type"],
        model_name=MODEL_NAME,
        model_version=f"{outcome.model}/{outcome.prompt_version}",
        accepted=accepted,
        inference_ms=round(elapsed_ms, 2),
        health=None,
        plant=plant,
        # Gemini is now the primary diagnosis, so there is no second opinion to
        # disagree with. ``gemini_agrees`` stays None, which hides the legacy
        # "disagreement" banner in the frontend.
        gemini_verdict=label,
        gemini_agrees=None,
        gemini_reasoning=d.summary,
        metadata=meta,
    )


def run_vision_prediction(
    image_bytes: bytes,
    *,
    identify: bool = True,
    species_id: str | None = None,
) -> VisionResult:
    """Diagnose one image with Gemini and return the legacy ``VisionResult`` shape.

    ``species_id`` (manual lock) is passed to Gemini as a hint and echoed back
    as a ``source='manual'`` identification. ``identify=False`` omits the plant
    block. Raises ``GeminiError`` / ``InvalidImageError`` (structured
    ``AppError``s) on failure; there is no local fallback.
    """

    t0 = time.perf_counter()
    hint = None
    if species_id and species_id.strip():
        entry = species_lookup(species_id)
        hint = entry.common_name if entry.species_id != "unknown" else species_id.strip()

    outcome = diagnose_plant_image(image_bytes, species_hint=hint)
    elapsed_ms = (time.perf_counter() - t0) * 1000.0
    result = vision_result_from_diagnosis(
        outcome, identify=identify, species_id=species_id, elapsed_ms=elapsed_ms
    )

    try:
        from services.metrics_store import METRICS_STORE

        METRICS_STORE.record(
            inference_ms=round(elapsed_ms, 2),
            model_source=f"gemini:{outcome.model}",
            image_size=list(outcome.image.original_size),
        )
    except Exception as exc:  # noqa: BLE001 - metrics must never fail a scan
        log.warning("failed to log scan metrics: %s", exc)

    return result
