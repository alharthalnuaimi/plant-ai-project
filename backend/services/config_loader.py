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
    return {
        "model": model_cfg,
        "thresholds": threshold_cfg,
        "survival": survival_cfg,
    }

