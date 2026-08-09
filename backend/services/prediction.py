from __future__ import annotations

import logging
import time

from schemas.contracts import PlantIdentification, VisionResult
from services.config_loader import get_runtime_config
from services.disease_taxonomy import classify_disease
from services.model_manager import ModelManager
from services.preprocess import should_preprocess, standardize_for_model
from services.species_taxonomy import lookup as species_lookup

log = logging.getLogger("plantvision.prediction")


def _identify_plant(
    image_bytes: bytes,
    *,
    manual_species_id: str | None = None,
) -> tuple[PlantIdentification | None, float]:
    """Run plant identification (Phase 3, plug-in seam).

    Returns (identification, elapsed_ms). When ``manual_species_id`` is set,
    the model is skipped and the manual selection is echoed back as a
    ``source='manual'`` identification — this keeps the API contract uniform
    regardless of whether the identity came from the user or a model.
    """

    t0 = time.perf_counter()

    if manual_species_id and manual_species_id.strip():
        entry = species_lookup(manual_species_id)
        return (
            PlantIdentification(
                species_id=entry.species_id,
                common_name=entry.common_name,
                scientific_name=entry.scientific_name,
                family=entry.family,
                confidence=1.0,  # user-asserted identity is treated as ground truth
                source="manual",
            ),
            round((time.perf_counter() - t0) * 1000.0, 2),
        )

    try:
        model = ModelManager.instance().get_plant_id_model()
        pid_pred = model.predict(image_bytes)
        return (
            PlantIdentification(
                species_id=pid_pred.species_id,
                common_name=pid_pred.common_name,
                scientific_name=pid_pred.scientific_name,
                family=pid_pred.family,
                genus=getattr(pid_pred, "genus", None),
                confidence=round(float(pid_pred.confidence), 4),
                source=pid_pred.source,
            ),
            round((time.perf_counter() - t0) * 1000.0, 2),
        )
    except Exception as exc:  # noqa: BLE001 — never fail /predict on identification
        log.warning("plant identification failed (non-fatal): %s", exc)
        return None, round((time.perf_counter() - t0) * 1000.0, 2)


def run_vision_prediction(
    image_bytes: bytes,
    *,
    identify: bool = True,
    species_id: str | None = None,
) -> VisionResult:
    """Run disease detection + (optional) plant identification on one image.

    Parameters
    ----------
    image_bytes : bytes
        Raw image content (JPEG/PNG/...).
    identify : bool, default True
        Disable to skip plant identification entirely (fastest path; useful
        for the ESP32 firmware that already knows the plant).
    species_id : str | None, default None
        When provided, the identifier is bypassed and the supplied species
        is echoed back with ``source='manual'``. Used by the Home scan UI
        when the user explicitly tags the plant.
    """

    t0 = time.perf_counter()
    if should_preprocess():
        image_bytes = standardize_for_model(image_bytes, output="jpeg_bytes")  # type: ignore[assignment]

    # 1. Plant identification (Phase 3, additive). Must happen first so we can route the disease model!
    plant: PlantIdentification | None = None
    plant_id_ms = 0.0
    species_str = "unknown"
    
    if identify or species_id:
        plant, plant_id_ms = _identify_plant(image_bytes, manual_species_id=species_id)
        if plant and plant.species_id:
            species_str = plant.species_id

    # 2. Disease detection (species-aware).
    predictor = ModelManager.instance().get_vision_model()
    pred = predictor.predict(image_bytes, species=species_str)
    inference_ms = (time.perf_counter() - t0) * 1000.0

    threshold = float(
        get_runtime_config()
        .get("thresholds", {})
        .get("prediction", {})
        .get("confidence_accept_threshold", 0.25)
    )
    accepted = pred.confidence >= threshold
    raw = pred.raw or {}
    model_name = str(raw.get("model", "unknown"))
    model_version = ModelManager.instance().active_versions(species_str).get("vision_version") or "unversioned"
    if "stub" in model_name:
        model_version = "stub"

    tax = classify_disease(pred.disease)

    # Record inference time metric (Phase 2)
    try:
        from services.metrics_store import METRICS_STORE
        img_size = raw.get("image_size", [640, 640]) if isinstance(raw, dict) else [640, 640]
        METRICS_STORE.record(
            inference_ms=round(inference_ms, 2),
            model_source=model_name,
            image_size=img_size,
        )
    except Exception as exc:
        log.warning("failed to log scan metrics: %s", exc)

    return VisionResult(
        disease=tax["display_label"],
        confidence=round(float(pred.confidence), 4),
        stress_hint=pred.stress_hint,
        class_name=tax["class_name"],
        disease_type=tax["disease_type"],
        model_name=model_name,
        model_version=model_version,
        accepted=accepted,
        inference_ms=round(inference_ms, 2),
        health=None,
        plant=plant,
        metadata={
            "threshold": threshold,
            "raw_disease_label": pred.disease,
            "plant_id_ms": plant_id_ms,
            **raw,
        },
    )
