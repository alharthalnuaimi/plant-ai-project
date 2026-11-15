"""Gemini intelligence service — the only AI path for diagnosis and reasoning.

    client.py     official google-genai client, timeouts, retries, error mapping
    config.py     env configuration (GEMINI_API_KEY, models, limits)
    images.py     validation + compression before upload
    diagnosis.py  multimodal plant diagnosis (structured JSON)
    reasoning.py  diagnosis × sensors × question reasoning (structured JSON)
    prompts.py    prompt text
    schemas.py    response contracts + consistency rules
    errors.py     structured, user-safe errors
"""

from services.gemini.client import GeminiClient, gemini_status, get_gemini_client, set_gemini_client
from services.gemini.config import GeminiConfig, load_gemini_config
from services.gemini.diagnosis import DiagnosisOutcome, clear_diagnosis_cache, diagnose_plant_image
from services.gemini.errors import GeminiError, GeminiNotConfigured, InvalidImageError
from services.gemini.reasoning import ReasoningOutcome, build_reasoning_context, reason_about_plant

__all__ = [
    "DiagnosisOutcome",
    "GeminiClient",
    "GeminiConfig",
    "GeminiError",
    "GeminiNotConfigured",
    "InvalidImageError",
    "ReasoningOutcome",
    "build_reasoning_context",
    "clear_diagnosis_cache",
    "diagnose_plant_image",
    "gemini_status",
    "get_gemini_client",
    "load_gemini_config",
    "reason_about_plant",
    "set_gemini_client",
]
