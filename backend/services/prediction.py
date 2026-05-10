from __future__ import annotations

import time

from schemas.contracts import VisionResult
from services.config_loader import get_runtime_config
from services.model_manager import ModelManager
from services.preprocess import should_preprocess, standardize_for_model


def run_vision_prediction(image_bytes: bytes) -> VisionResult:
    t0 = time.perf_counter()
    if should_preprocess():
        image_bytes = standardize_for_model(image_bytes, output="jpeg_bytes")  # type: ignore[assignment]
    predictor = ModelManager.instance().get_vision_model()
    pred = predictor.predict(image_bytes)
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
    model_version = ModelManager.instance().active_versions().get("vision_version") or "unversioned"
    if model_name == "stub_vision":
        model_version = "stub"

    return VisionResult(
        disease=pred.disease,
        confidence=round(float(pred.confidence), 4),
        stress_hint=pred.stress_hint,
        model_name=model_name,
        model_version=model_version,
        accepted=accepted,
        inference_ms=round(inference_ms, 2),
        metadata={
            "threshold": threshold,
            **raw,
        },
    )
