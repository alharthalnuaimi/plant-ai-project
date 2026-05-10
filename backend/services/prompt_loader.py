from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from config.paths import BACKEND_DIR


PROMPTS_DIR = BACKEND_DIR / "prompts"


@lru_cache(maxsize=16)
def load_prompt(name: str) -> str:
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8").strip()

