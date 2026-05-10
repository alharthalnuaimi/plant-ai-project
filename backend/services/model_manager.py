from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

from models.disease_model import VisionPredictor, get_vision_predictor
from models.llama_model import LlamaClient, get_llama_client
from services.config_loader import get_runtime_config
from services.model_registry import resolve_model_descriptor


@dataclass
class ModelHealth:
    vision_loaded: bool
    llama_loaded: bool
    vision_version: str
    llama_model: str | None


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

    def active_versions(self) -> dict[str, Any]:
        descriptor = resolve_model_descriptor()
        llama = self.get_llama_model()
        return {
            "vision_version": descriptor.version,
            "vision_source": descriptor.source,
            "llama_model": None if llama is None else llama.model,
            "prompt_version": (
                get_runtime_config().get("model", {}).get("llama", {}).get("prompt_version", "v1")
            ),
        }

    def health_status(self) -> ModelHealth:
        descriptor = resolve_model_descriptor()
        llama = self._llama_client
        return ModelHealth(
            vision_loaded=self._vision_model is not None,
            llama_loaded=llama is not None,
            vision_version=descriptor.version,
            llama_model=None if llama is None else llama.model,
        )

