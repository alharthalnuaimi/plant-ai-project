"""Centralised Gemini API client (official ``google-genai`` SDK).

* One process-wide client built from ``GEMINI_API_KEY``.
* Request timeout, bounded retries with exponential backoff + jitter for
  transient failures (5xx, timeouts, network errors, per-minute rate
  limits). Authentication, quota-exhausted, bad-request and safety errors
  are never retried.
* Safety blocks, truncated output and malformed JSON become structured
  ``GeminiError`` subclasses; nothing is silently replaced by canned text.
* Logs model, latency and token counts per call. Never logs the key,
  prompts, images or model output.
"""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from services.gemini.config import GeminiConfig, load_gemini_config
from services.gemini.errors import (
    GeminiAuthError,
    GeminiBadRequest,
    GeminiError,
    GeminiInvalidResponse,
    GeminiModelNotFound,
    GeminiNetworkError,
    GeminiNotConfigured,
    GeminiQuotaExceeded,
    GeminiRateLimited,
    GeminiSafetyBlocked,
    GeminiTimeout,
    GeminiUnavailable,
)

log = logging.getLogger("plantvision.gemini")

M = TypeVar("M", bound=BaseModel)

_SAFETY_FINISH_REASONS = {
    "SAFETY",
    "PROHIBITED_CONTENT",
    "BLOCKLIST",
    "SPII",
    "IMAGE_SAFETY",
    "RECITATION",
}


# Below this much time left before the deadline, a retry is not attempted.
_MIN_ATTEMPT_S = 3.0


def _is_gemini3(model: str) -> bool:
    """True for Gemini 3.x and later, which use thinking_level and the default temperature."""
    name = model.rsplit("/", 1)[-1]
    if not name.startswith("gemini-"):
        return False
    major = name[len("gemini-"):].split(".", 1)[0].split("-", 1)[0]
    return major.isdigit() and int(major) >= 3


@dataclass
class GeminiCallInfo:
    operation: str
    model: str
    attempts: int
    latency_ms: float
    prompt_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "model": self.model,
            "attempts": self.attempts,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }


# --------------------------------------------------------------------------
# Error classification
# --------------------------------------------------------------------------


def _enum_name(value: Any) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", None)
    return str(name if name else value).upper().split(".")[-1]


def classify_exception(exc: BaseException, model: str = "") -> GeminiError:
    """Map SDK / transport exceptions onto user-safe ``GeminiError`` types."""

    if isinstance(exc, GeminiError):
        return exc

    try:
        from google.genai import errors as genai_errors
    except Exception:  # pragma: no cover - SDK is a hard dependency
        genai_errors = None  # type: ignore[assignment]

    if genai_errors is not None and isinstance(exc, genai_errors.APIError):
        code = int(getattr(exc, "code", 0) or 0)
        text = " ".join(
            str(x)
            for x in (getattr(exc, "status", ""), getattr(exc, "message", ""), getattr(exc, "details", ""))
            if x
        ).lower()
        if code in (401, 403) or "api_key_invalid" in text or "api key not valid" in text:
            return GeminiAuthError()
        if code == 429:
            if "perday" in text or "per_day" in text or "per day" in text or "billing" in text:
                return GeminiQuotaExceeded()
            return GeminiRateLimited()
        if code == 404:
            log.warning("Gemini model %r is not available to this key (404)", model)
            return GeminiModelNotFound()
        if code == 400:
            if "api key" in text:
                return GeminiAuthError()
            return GeminiBadRequest()
        if code == 504:
            return GeminiTimeout()
        if code >= 500:
            return GeminiUnavailable()
        return GeminiError()

    try:
        import httpx

        if isinstance(exc, httpx.TimeoutException):
            return GeminiTimeout()
        if isinstance(exc, httpx.TransportError):
            return GeminiNetworkError()
    except Exception:  # pragma: no cover
        pass

    if isinstance(exc, TimeoutError):
        return GeminiTimeout()
    if isinstance(exc, (ConnectionError, OSError)):
        return GeminiNetworkError()
    return GeminiError()


def _usage(response: Any) -> tuple[int | None, int | None, int | None]:
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return None, None, None
    return (
        getattr(meta, "prompt_token_count", None),
        getattr(meta, "candidates_token_count", None),
        getattr(meta, "total_token_count", None),
    )


def extract_text(response: Any) -> str:
    """Return the text of a response, or raise a structured error explaining why there is none."""

    feedback = getattr(response, "prompt_feedback", None)
    block_reason = _enum_name(getattr(feedback, "block_reason", None)) if feedback else ""
    if block_reason and block_reason not in ("BLOCK_REASON_UNSPECIFIED", "NONE"):
        raise GeminiSafetyBlocked()

    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        raise GeminiInvalidResponse("The AI service returned no answer. Please retry.")

    finish = _enum_name(getattr(candidates[0], "finish_reason", None))
    if finish in _SAFETY_FINISH_REASONS:
        raise GeminiSafetyBlocked()

    parts = getattr(getattr(candidates[0], "content", None), "parts", None) or []
    text = "".join(
        (getattr(p, "text", None) or "") for p in parts if not getattr(p, "thought", False)
    ).strip()

    if finish == "MAX_TOKENS":
        raise GeminiInvalidResponse(
            "The AI answer was cut off (output token limit). Raise GEMINI_MAX_OUTPUT_TOKENS or retry."
        )
    if not text:
        raise GeminiInvalidResponse("The AI service returned an empty answer. Please retry.")
    return text


def parse_json_model(text: str, schema: type[M]) -> M:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = "\n".join(line for line in cleaned.splitlines() if not line.strip().startswith("```"))
    try:
        return schema.model_validate_json(cleaned)
    except (ValidationError, json.JSONDecodeError, ValueError) as exc:
        log.warning(
            "Gemini JSON failed validation for %s (%s)", schema.__name__, type(exc).__name__
        )
        raise GeminiInvalidResponse() from exc


# --------------------------------------------------------------------------
# Client
# --------------------------------------------------------------------------


class GeminiClient:
    def __init__(
        self,
        config: GeminiConfig,
        sdk_client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not config.configured:
            raise GeminiNotConfigured()
        self.config = config
        self._sleep = sleep
        self._sdk = sdk_client if sdk_client is not None else self._build_sdk(config)

    @staticmethod
    def _build_sdk(config: GeminiConfig) -> Any:
        from google import genai
        from google.genai import types

        http_kwargs: dict[str, Any] = {"timeout": int(config.timeout_s * 1000)}
        # Retries are handled here (with our own classification), so turn the
        # SDK's built-in retrying off to avoid multiplying attempts.
        if hasattr(types, "HttpRetryOptions"):
            http_kwargs["retry_options"] = types.HttpRetryOptions(attempts=1)
        return genai.Client(api_key=config.api_key, http_options=types.HttpOptions(**http_kwargs))

    # ---- request construction ------------------------------------------

    def _build_config(
        self,
        *,
        model: str,
        system_instruction: str | None,
        temperature: float,
        response_schema: type[BaseModel] | None,
        timeout_s: float | None = None,
    ) -> Any:
        from google.genai import types

        gemini3 = _is_gemini3(model)
        kwargs: dict[str, Any] = {"max_output_tokens": self.config.max_output_tokens}
        # Google advises leaving temperature at its default on Gemini 3.x; lower values can loop.
        if not gemini3:
            kwargs["temperature"] = temperature
        if timeout_s is not None:
            kwargs["http_options"] = types.HttpOptions(timeout=max(1000, int(timeout_s * 1000)))
        if system_instruction:
            kwargs["system_instruction"] = system_instruction
        if response_schema is not None:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_schema"] = response_schema
        # Gemini 3.x takes thinking_level; sending thinking_budget as well is an API error.
        if gemini3 and self.config.thinking_level:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=self.config.thinking_level.upper())
        elif not gemini3 and self.config.thinking_budget is not None:
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=self.config.thinking_budget)
        return types.GenerateContentConfig(**kwargs)

    @staticmethod
    def image_part(data: bytes, mime_type: str) -> Any:
        from google.genai import types

        return types.Part.from_bytes(data=data, mime_type=mime_type)

    # ---- calls -----------------------------------------------------------

    def _backoff(self, attempt: int) -> float:
        delay = min(self.config.backoff_max_s, self.config.backoff_base_s * (2 ** attempt))
        return delay * (0.5 + random.random() * 0.5)

    def generate_text(
        self,
        *,
        operation: str,
        model: str,
        contents: list[Any],
        system_instruction: str | None = None,
        temperature: float = 0.3,
        response_schema: type[BaseModel] | None = None,
    ) -> tuple[str, GeminiCallInfo]:
        t0 = time.perf_counter()
        deadline = t0 + self.config.deadline_s
        current = model
        attempt = 0
        while True:
            attempt += 1
            gen_config = self._build_config(
                model=current,
                system_instruction=system_instruction,
                temperature=temperature,
                response_schema=response_schema,
                timeout_s=min(self.config.timeout_s, deadline - time.perf_counter()),
            )
            try:
                response = self._sdk.models.generate_content(
                    model=current, contents=contents, config=gen_config
                )
                text = extract_text(response)
            except Exception as exc:  # noqa: BLE001 - classified below
                err = classify_exception(exc, current)
                fallback = self.config.fallback_model
                fallback = fallback if fallback and fallback != current else None
                retry = err.retryable or (fallback is not None and isinstance(err, GeminiModelNotFound))
                left = deadline - time.perf_counter()
                if retry and attempt <= self.config.max_retries and left > _MIN_ATTEMPT_S:
                    delay = min(self._backoff(attempt - 1), left - _MIN_ATTEMPT_S)
                    log.warning(
                        "gemini op=%s model=%s attempt=%d failed (%s); retrying on %s in %.1fs",
                        operation, current, attempt, err.code, fallback or current, delay,
                    )
                    self._sleep(delay)
                    current = fallback or current
                    continue
                log.warning(
                    "gemini op=%s model=%s failed after %d attempt(s): %s (%s)",
                    operation, current, attempt, err.code, type(exc).__name__,
                )
                _record_health(not isinstance(err, _MODEL_DOWN_ERRORS), current, err.code)
                if err is exc:
                    raise
                raise err from exc

            prompt_t, output_t, total_t = _usage(response)
            _record_health(True, current, None)
            info = GeminiCallInfo(
                operation=operation,
                model=current,
                attempts=attempt,
                latency_ms=round((time.perf_counter() - t0) * 1000.0, 1),
                prompt_tokens=prompt_t,
                output_tokens=output_t,
                total_tokens=total_t,
            )
            log.info(
                "gemini op=%s model=%s attempts=%d latency_ms=%.0f tokens prompt=%s output=%s total=%s",
                operation, model, attempt, info.latency_ms, prompt_t, output_t, total_t,
            )
            return text, info

    def generate_json(
        self,
        *,
        operation: str,
        model: str,
        contents: list[Any],
        schema: type[M],
        system_instruction: str | None = None,
        temperature: float = 0.3,
    ) -> tuple[M, GeminiCallInfo]:
        text, info = self.generate_text(
            operation=operation,
            model=model,
            contents=contents,
            system_instruction=system_instruction,
            temperature=temperature,
            response_schema=schema,
        )
        return parse_json_model(text, schema), info


# --------------------------------------------------------------------------
# Process-wide accessor
# --------------------------------------------------------------------------

_lock = threading.Lock()
_client: GeminiClient | None = None
_client_key: tuple | None = None
_injected: GeminiClient | None = None


def get_gemini_client() -> GeminiClient:
    """Return the shared client. Raises ``GeminiNotConfigured`` when the key is missing."""

    global _client, _client_key
    if _injected is not None:
        return _injected
    config = load_gemini_config()
    if not config.configured:
        raise GeminiNotConfigured()
    # The SDK client only depends on the key and timeout; other settings
    # (models, retries, temperatures) are refreshed in place.
    key = (config.api_key, config.timeout_s)
    with _lock:
        if _client is None or _client_key != key:
            _client = GeminiClient(config)
            _client_key = key
        elif _client.config != config:
            _client.config = config
        return _client


def set_gemini_client(client: GeminiClient | None) -> None:
    """Inject a client for tests (``None`` clears the injection, the cache and the health result)."""

    global _client, _client_key, _injected, _health
    with _lock:
        _injected = client
        _client = None
        _client_key = None
        _health = None


# --------------------------------------------------------------------------
# Real readiness check
# --------------------------------------------------------------------------
# A key can be accepted and a model can appear in the model list while
# generating still fails, so readiness comes from an actual call. Every real
# call updates it, and a one-line probe runs only when nothing has run lately.

HEALTH_MAX_AGE_S = 600.0
# Errors meaning the AI path is down, as opposed to a problem with one request.
_MODEL_DOWN_ERRORS = (
    GeminiAuthError,
    GeminiModelNotFound,
    GeminiUnavailable,
    GeminiTimeout,
    GeminiNetworkError,
    GeminiQuotaExceeded,
    GeminiRateLimited,
)
_health: dict[str, Any] | None = None
_health_lock = threading.Lock()


def _record_health(ok: bool, model: str, error: str | None) -> None:
    global _health
    _health = {"ok": ok, "model": model, "error": error, "checked_at": time.time()}


def check_gemini_ready(max_age_s: float = HEALTH_MAX_AGE_S) -> dict[str, Any]:
    """``status`` is live, unavailable or not_configured, from a real call at most ``max_age_s`` old."""

    config = load_gemini_config()
    if not config.configured:
        return {"status": "not_configured", "model": config.diagnosis_model, "error": None, "checked_at": None}
    with _health_lock:
        if _health is None or time.time() - _health["checked_at"] > max_age_s:
            try:
                get_gemini_client().generate_text(
                    operation="health_check",
                    model=config.diagnosis_model,
                    contents=["Reply with the word OK."],
                )
            except GeminiError:
                pass  # recorded by generate_text
        h = _health or {"ok": False, "model": config.diagnosis_model, "error": "gemini_error", "checked_at": time.time()}
    return {
        "status": "live" if h["ok"] else "unavailable",
        "model": h["model"],
        "error": h["error"],
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(h["checked_at"])),
    }


def gemini_status() -> dict[str, Any]:
    return load_gemini_config().public_summary()
