from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from models.disease_model import VisionPredictor, get_vision_predictor
from models.llama_model import LlamaClient, get_llama_client
from models.plant_id_model import PlantIdPredictor, get_plant_id_predictor
from services.config_loader import get_runtime_config
from services.model_registry import resolve_model_descriptor


@dataclass
class ModelHealth:
    vision_loaded: bool
    llama_loaded: bool
    plant_id_loaded: bool
    vision_version: str
    llama_model: str | None
    plant_id_source: str | None


class ModelManager:
    """
    Lightweight singleton model cache for MVP:
    - lazy loads predictor/client
    - keeps one in-memory instance per process
    - exposes health and active versions
    """

    _instance: "ModelManager | None" = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._vision_model: VisionPredictor | None = None
        self._llama_client: LlamaClient | None = None
        # Phase 3 — separate plant identification model. Lazy-loaded on first
        # /predict that requests it (or on /report). Stub by default; pluggable
        # later via PLANT_ID_MODEL env.
        self._plant_id_model: PlantIdPredictor | None = None
        self._plant_id_source: str | None = None

    @classmethod
    def instance(cls) -> "ModelManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
        return cls._instance

    def get_vision_model(self) -> VisionPredictor:
        with self._lock:
            if self._vision_model is None:
                self._vision_model = get_vision_predictor()
            return self._vision_model

    def get_llama_model(self) -> LlamaClient | None:
        with self._lock:
            if self._llama_client is None:
                self._llama_client = get_llama_client()
            return self._llama_client

    def get_plant_id_model(self) -> PlantIdPredictor:
        """Lazily load the plant-identification model (singleton per process)."""

        with self._lock:
            if self._plant_id_model is None:
                self._plant_id_model = get_plant_id_predictor()
                self._plant_id_source = self._plant_id_model.__class__.__name__
            return self._plant_id_model

    def active_versions(self, species: str = "unknown") -> dict[str, Any]:
        descriptor = resolve_model_descriptor(species)
        llama = self.get_llama_model()
        return {
            "vision_version": descriptor.version,
            "vision_source": descriptor.source,
            "llama_model": None if llama is None else llama.model,
            "plant_id_source": self._plant_id_source,
            "prompt_version": (
                get_runtime_config().get("model", {}).get("llama", {}).get("prompt_version", "v1")
            ),
        }

    def health_status(self) -> ModelHealth:
        # In a multi-species world, "health" is more complex. For MVP healthcheck,
        # we'll just check if the model router initialized (it always does).
        # We pass "unknown" to the descriptor to avoid TypeError, though it's
        # less meaningful globally now.
        descriptor = resolve_model_descriptor("unknown")
        llama = self._llama_client
        return ModelHealth(
            vision_loaded=self._vision_model is not None,
            llama_loaded=llama is not None,
            plant_id_loaded=self._plant_id_model is not None,
            vision_version=descriptor.version,
            llama_model=None if llama is None else llama.model,
            plant_id_source=self._plant_id_source,
        )

