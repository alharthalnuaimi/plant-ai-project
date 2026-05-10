"""
Resolve production weights: explicit env wins, then artifacts/registry.json `active`.
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
        return {"active": None, "versions": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"active": None, "versions": {}}


def resolve_weights_path() -> str | None:
    env_w = os.getenv("YOLO_WEIGHTS_PATH", "").strip()
    if env_w and Path(env_w).is_file():
        return env_w

    reg = load_registry()
    active = reg.get("active")
    if not active:
        return None
    ver = (reg.get("versions") or {}).get(active)
    if not ver:
        return None
    rel = ver.get("weights_relative") or ver.get("weights")
    if not rel:
        return None
    candidate = (REPO_ROOT / str(rel)).resolve()
    if candidate.is_file():
        return str(candidate)
    return None


def resolve_active_version() -> str | None:
    reg = load_registry()
    return reg.get("active")


def resolve_model_descriptor() -> ModelDescriptor:
    env_w = os.getenv("YOLO_WEIGHTS_PATH", "").strip()
    if env_w and Path(env_w).is_file():
        return ModelDescriptor(
            version="env_override",
            weights_path=env_w,
            source="env",
            metadata={},
        )

    reg = load_registry()
    active = reg.get("active")
    if active:
        entry = (reg.get("versions") or {}).get(active) or {}
        rel = entry.get("weights_relative") or entry.get("weights")
        if rel:
            candidate = (REPO_ROOT / str(rel)).resolve()
            if candidate.is_file():
                return ModelDescriptor(
                    version=str(active),
                    weights_path=str(candidate),
                    source="registry",
                    metadata=entry,
                )

    return ModelDescriptor(
        version="stub",
        weights_path=None,
        source="fallback_stub",
        metadata={"reason": "No valid env/registry model found"},
    )
