from __future__ import annotations

from fastapi import APIRouter

from services.dataset_config import dataset_info, default_data_yaml_path, get_yolo_class_names
from services.model_manager import ModelManager
from services.model_registry import (
    load_registry,
    registry_path,
    resolve_model_descriptor,
)

router = APIRouter(tags=["dataset"])


@router.get("/dataset/info")
async def api_dataset_info() -> dict:
    """Introspect local dataset layout and class names (no image bytes returned)."""
    return dataset_info()


@router.get("/dataset/classes")
async def api_dataset_classes() -> dict:
    names = get_yolo_class_names()
    return {
        "source": str(default_data_yaml_path()),
        "names": names,
        "count": len(names),
    }


@router.get("/models/health")
async def api_models_health() -> dict:
    mm = ModelManager.instance()
    h = mm.health_status()
    return {
        "vision_loaded": h.vision_loaded,
        "llama_loaded": h.llama_loaded,
        "vision_version": h.vision_version,
        "llama_model": h.llama_model,
        "active_versions": mm.active_versions("unknown"),
    }


@router.get("/models/registry")
async def api_models_registry() -> dict:
    reg = load_registry()
    descriptor = resolve_model_descriptor("unknown")
    return {
        "registry_path": str(registry_path()),
        "active_version": "multi-species-router",
        "resolved_weights": descriptor.weights_path,
        "resolved_model": {
            "version": descriptor.version,
            "weights_path": descriptor.weights_path,
            "source": descriptor.source,
            "metadata": descriptor.metadata,
        },
        "registry": reg,
    }
