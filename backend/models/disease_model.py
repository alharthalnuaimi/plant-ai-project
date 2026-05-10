"""
Vision-only plant disease / stress signals.

Llama must never classify images; this module is the only image path.
Swap `StubVisionPredictor` for `YoloVisionPredictor` when weights are available.
"""

from __future__ import annotations

import io
import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from PIL import Image

from services.dataset_config import get_yolo_class_names
from services.model_registry import resolve_model_descriptor


@dataclass
class DiseasePrediction:
    disease: str
    confidence: float
    stress_hint: str  # e.g. dehydration proxy from simple heuristics in stub
    raw: dict[str, Any]


class VisionPredictor(ABC):
    @abstractmethod
    def predict(self, image_bytes: bytes) -> DiseasePrediction:
        ...


class StubVisionPredictor(VisionPredictor):
    """
    MVP placeholder: validates image, derives a crude brightness/greenness hint for stress demo,
    and picks a demo disease label for API shape. Replace with YOLO for real demos.
    """

    _DEMO_DISEASES = [
        ("Healthy", 0.15),
        ("Powdery Mildew", 0.12),
        ("Leaf Spot", 0.10),
        ("Rust", 0.08),
        ("Blight", 0.06),
    ]

    @staticmethod
    def _label_choices() -> list[tuple[str, float]]:
        names = get_yolo_class_names()
        if names:
            return [(n, 0.12) for n in names]
        return list(StubVisionPredictor._DEMO_DISEASES)

    def predict(self, image_bytes: bytes) -> DiseasePrediction:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        # Downsample for cheap stats
        small = img.resize((min(w, 64), min(h, 64)))
        pixels = list(small.getdata())
        if not pixels:
            raise ValueError("Empty image")

        r = sum(p[0] for p in pixels) / len(pixels)
        g = sum(p[1] for p in pixels) / len(pixels)
        b = sum(p[2] for p in pixels) / len(pixels)
        brightness = (r + g + b) / 3.0
        green_ratio = g / max(r + g + b, 1e-6)

        # Heuristic stress hint (not a scientific model — demo only)
        if brightness > 200 and green_ratio < 0.34:
            stress_hint = "possible_dehydration_or_sun_stress"
        elif green_ratio < 0.30:
            stress_hint = "low_vigor_or_yellowing"
        else:
            stress_hint = "no_strong_visual_stress_signal"

        rng = random.Random(hash(image_bytes[:4096]) % (2**32))
        disease, base_p = rng.choice(self._label_choices())
        # Nudge confidence with heuristic (still stub)
        confidence = min(0.95, max(0.35, base_p + (0.15 if "stress" in stress_hint else 0.0)))

        raw = {
            "model": "stub_vision",
            "label_source": "dataset/yolov8/data.yaml" if get_yolo_class_names() else "builtin_demo",
            "brightness": round(brightness, 2),
            "green_ratio": round(green_ratio, 4),
            "image_size": [w, h],
        }
        return DiseasePrediction(
            disease=disease,
            confidence=float(confidence),
            stress_hint=stress_hint,
            raw=raw,
        )


class YoloVisionPredictor(VisionPredictor):
    """
    Optional real detector. Weights from YOLO_WEIGHTS_PATH or artifacts/registry.json.
    Install ultralytics in the runtime if you use this class.
    """

    def __init__(self, weights_path: str) -> None:
        from ultralytics import YOLO  # type: ignore import-not-found

        self._weights_path = weights_path
        self._model = YOLO(weights_path)
        self._conf = float(os.getenv("YOLO_CONF", "0.25"))
        self._imgsz = int(os.getenv("YOLO_IMGSZ", "640"))

    def predict(self, image_bytes: bytes) -> DiseasePrediction:
        from ultralytics import YOLO  # noqa: F401 — side effect: ensures dep present

        results = self._model.predict(
            source=image_bytes,
            verbose=False,
            conf=self._conf,
            imgsz=self._imgsz,
        )
        if not results:
            raise RuntimeError("YOLO returned no results")

        r0 = results[0]
        names = r0.names or {}
        if r0.probs is not None:
            top1 = int(r0.probs.top1)
            conf = float(r0.probs.top1conf)
            label = names.get(top1, str(top1))
        elif r0.boxes is not None and len(r0.boxes):
            i = int(r0.boxes.conf.argmax())
            conf = float(r0.boxes.conf[i])
            cls = int(r0.boxes.cls[i])
            label = names.get(cls, str(cls))
        else:
            label = "Unknown"
            conf = 0.0

        raw = {
            "model": "yolov8",
            "weights": self._weights_path,
            "conf": self._conf,
            "imgsz": self._imgsz,
        }
        return DiseasePrediction(
            disease=label,
            confidence=conf,
            stress_hint="from_yolo_only",
            raw=raw,
        )


def get_vision_predictor() -> VisionPredictor:
    descriptor = resolve_model_descriptor()
    weights = descriptor.weights_path
    if weights and os.path.isfile(weights):
        try:
            return YoloVisionPredictor(weights)
        except Exception:
            pass
    return StubVisionPredictor()
