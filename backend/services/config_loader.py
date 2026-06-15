from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from config.paths import REPO_ROOT


CONFIG_DIR = REPO_ROOT / "configs"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def get_runtime_config() -> dict[str, Any]:
    model_cfg = _load_yaml(CONFIG_DIR / "model.yaml")
    threshold_cfg = _load_yaml(CONFIG_DIR / "thresholds.yaml")
    survival_cfg = _load_yaml(CONFIG_DIR / "survival_weights.yaml")
    care_cfg = _load_yaml(CONFIG_DIR / "care_templates.yaml")
    return {
        "model": model_cfg,
        "thresholds": threshold_cfg,
        "survival": survival_cfg,
        "care_templates": care_cfg,
    }


def get_care_templates() -> dict[str, Any]:
    """Direct accessor for the care-templates block (Phase 3).

    Kept as a thin wrapper around ``get_runtime_config`` so callers don't
    need to know the YAML key. Returns ``{}`` when the file is missing.
    """

    return get_runtime_config().get("care_templates", {}) or {}

