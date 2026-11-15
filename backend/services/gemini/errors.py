"""Structured Gemini failures.

Every error is an ``AppError`` so the global FastAPI handler in ``main.py``
turns it into ``{"error": <code>, "message": <text>, "request_id": ...}``
with the right HTTP status. Messages are written for end users and never
contain the API key or the raw upstream response.
"""

from __future__ import annotations

from core.errors import AppError


class GeminiError(AppError):
    code = "gemini_error"
    status = 502
    retryable = False
    default_message = "The AI service returned an error. Please try again."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(self.code, message or self.default_message, self.status)


class GeminiNotConfigured(GeminiError):
    code = "gemini_not_configured"
    status = 503
    default_message = (
        "AI diagnosis is not configured on the server (GEMINI_API_KEY is missing)."
    )


class GeminiAuthError(GeminiError):
    code = "gemini_auth_failed"
    status = 502
    default_message = "The server's Gemini API key was rejected. Check GEMINI_API_KEY."


class GeminiQuotaExceeded(GeminiError):
    code = "gemini_quota_exceeded"
    status = 429
    default_message = "The Gemini API quota is used up. Try again later."


class GeminiRateLimited(GeminiError):
    code = "gemini_rate_limited"
    status = 429
    retryable = True
    default_message = "The AI service is busy (rate limited). Please retry in a moment."


class GeminiUnavailable(GeminiError):
    code = "gemini_unavailable"
    status = 503
    retryable = True
    default_message = "The AI service is temporarily unavailable. Please retry."


class GeminiTimeout(GeminiError):
    code = "gemini_timeout"
    status = 504
    retryable = True
    default_message = "The AI service took too long to respond. Please retry."


class GeminiNetworkError(GeminiError):
    code = "gemini_network_error"
    status = 503
    retryable = True
    default_message = "Could not reach the AI service. Check the server's network and retry."


class GeminiSafetyBlocked(GeminiError):
    code = "gemini_safety_blocked"
    status = 422
    default_message = (
        "The AI service declined to analyse this request for safety reasons. "
        "Try a different photo of the plant."
    )


class GeminiInvalidResponse(GeminiError):
    code = "gemini_invalid_response"
    status = 502
    default_message = "The AI service returned an unusable answer. Please retry."


class GeminiBadRequest(GeminiError):
    code = "gemini_bad_request"
    status = 400
    default_message = "The AI service could not process this request (invalid input)."


class InvalidImageError(AppError):
    def __init__(self, message: str, status_code: int = 400, code: str = "invalid_image") -> None:
        super().__init__(code, message, status_code)


class ImageTooLargeError(InvalidImageError):
    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            f"Image is larger than the {max_bytes // (1024 * 1024)} MB upload limit.",
            status_code=413,
            code="image_too_large",
        )
