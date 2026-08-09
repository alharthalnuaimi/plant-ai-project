"""
Resolve production weights from the per-species registry or environment variable overrides.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.paths import REPO_ROOT


@dataclass
class ModelDescriptor:
    version: str
    weights_path: str | None
    source: str
    metadata: dict[str, Any]


def registry_path() -> Path:
    override = os.getenv("MODEL_REGISTRY_PATH", "").strip()
    if override:
        return Path(override)
    return REPO_ROOT / "artifacts" / "registry.json"


def load_registry() -> dict:
    p = registry_path()
    if not p.is_file():
        return {"species": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"species": {}}


def resolve_model_descriptor(species: str) -> ModelDescriptor:
    """Resolve the weights path and descriptor for a given species."""
    
    # 1. Environment variable override (e.g. ROSE_WEIGHTS_PATH)
    env_var_name = f"{species.upper()}_WEIGHTS_PATH"
    env_w = os.getenv(env_var_name, "").strip()
    if env_w and Path(env_w).is_file():
        return ModelDescriptor(
            version="env_override",
            weights_path=env_w,
            source="env",
            metadata={"species": species, "local_model_trusted": True},
        )

    # 2. Registry lookup
    reg = load_registry()
    species_config = reg.get("species", {}).get(species, {})
    local_model_trusted = species_config.get("local_model_trusted", False)
    
    rel_weights = species_config.get("weights_relative")
    if rel_weights:
        candidate = (REPO_ROOT / str(rel_weights)).resolve()
        if candidate.is_file():
            return ModelDescriptor(
                version=species_config.get("historical_training", {}).get("version", "registry"),
                weights_path=str(candidate),
                source="registry",
                metadata={"species": species, **species_config},
            )

    return ModelDescriptor(
        version="stub",
        weights_path=None,
        source="fallback_stub",
        metadata={"reason": f"No valid env/registry model found for {species}"},
    )
