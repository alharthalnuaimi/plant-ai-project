"""Gemini runtime configuration, read from environment variables.

One API key (``GEMINI_API_KEY``) powers every Gemini call. Diagnosis and
reasoning can use different models (``GEMINI_DIAGNOSIS_MODEL`` /
``GEMINI_REASONING_MODEL``); both default to ``GEMINI_MODEL``.

The key is held in a field excluded from ``repr`` so it never reaches logs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_MODEL = "gemini-3.5-flash"
# Used for the one retry when the main model is overloaded, times out or is not available.
DEFAULT_FALLBACK_MODEL = "gemini-3.5-flash-lite"


def _env_str(name: str, default: str = "") -> str:
    raw = os.getenv(name)
    return raw.strip() if raw and raw.strip() else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env_str(name, str(default)))
    except ValueError:
        return default


def _env_opt_int(name: str) -> int | None:
    raw = _env_str(name)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str = field(repr=False)
    diagnosis_model: str = DEFAULT_MODEL
    reasoning_model: str = DEFAULT_MODEL
    fallback_model: str = DEFAULT_FALLBACK_MODEL
    timeout_s: float = 25.0
    deadline_s: float = 30.0
    max_retries: int = 1
    backoff_base_s: float = 1.0
    backoff_max_s: float = 8.0
    diagnosis_temperature: float = 0.2
    reasoning_temperature: float = 0.4
    max_output_tokens: int = 8192
    thinking_budget: int | None = None
    thinking_level: str | None = None
    max_image_side: int = 1536
    jpeg_quality: int = 85
    max_upload_bytes: int = 10 * 1024 * 1024
    cache_ttl_s: int = 3600
    cache_max_entries: int = 256

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def public_summary(self) -> dict:
        """Safe to return from an API: no credentials."""
        return {
            "configured": self.configured,
            "diagnosis_model": self.diagnosis_model,
            "reasoning_model": self.reasoning_model,
            "fallback_model": self.fallback_model or None,
            "timeout_s": self.timeout_s,
            "deadline_s": self.deadline_s,
            "max_retries": self.max_retries,
        }


def load_gemini_config() -> GeminiConfig:
    base_model = _env_str("GEMINI_MODEL", DEFAULT_MODEL)
    return GeminiConfig(
        api_key=_env_str("GEMINI_API_KEY"),
        diagnosis_model=_env_str("GEMINI_DIAGNOSIS_MODEL", base_model),
        reasoning_model=_env_str("GEMINI_REASONING_MODEL", base_model),
        # "none" turns the fallback off.
        fallback_model="" if _env_str("GEMINI_FALLBACK_MODEL").lower() == "none"
        else _env_str("GEMINI_FALLBACK_MODEL", DEFAULT_FALLBACK_MODEL),
        timeout_s=max(1.0, _env_float("GEMINI_TIMEOUT_SECONDS", 25.0)),
        deadline_s=max(5.0, _env_float("GEMINI_DEADLINE_SECONDS", 30.0)),
        max_retries=max(0, _env_int("GEMINI_MAX_RETRIES", 1)),
        backoff_base_s=max(0.0, _env_float("GEMINI_BACKOFF_BASE_SECONDS", 1.0)),
        backoff_max_s=max(0.0, _env_float("GEMINI_BACKOFF_MAX_SECONDS", 8.0)),
        diagnosis_temperature=_env_float("GEMINI_DIAGNOSIS_TEMPERATURE", 0.2),
        reasoning_temperature=_env_float("GEMINI_REASONING_TEMPERATURE", 0.4),
        max_output_tokens=max(256, _env_int("GEMINI_MAX_OUTPUT_TOKENS", 8192)),
        thinking_budget=_env_opt_int("GEMINI_THINKING_BUDGET"),
        thinking_level=_env_str("GEMINI_THINKING_LEVEL").lower() or None,
        max_image_side=max(256, _env_int("GEMINI_MAX_IMAGE_SIDE", 1536)),
        jpeg_quality=min(95, max(40, _env_int("GEMINI_JPEG_QUALITY", 85))),
        max_upload_bytes=max(1024, _env_int("MAX_UPLOAD_BYTES", 10 * 1024 * 1024)),
        cache_ttl_s=max(0, _env_int("GEMINI_CACHE_TTL_SECONDS", 3600)),
        cache_max_entries=max(0, _env_int("GEMINI_CACHE_MAX_ENTRIES", 256)),
    )
