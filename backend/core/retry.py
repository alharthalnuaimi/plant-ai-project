"""
Lightweight async retry helper for repository / IO operations.

Phase 3 hardening: transient Postgres / pgbouncer errors (connection drops,
"server closed the connection unexpectedly", brief network blips) used to
silently fail and return False/None to the caller. This module gives the
repository layer a *small*, dependency-free retry decorator with structured
logging so every retry leaves a breadcrumb in the application log.

Design goals
------------
* No new third-party dependency (avoid adding `tenacity` for this).
* Async-only — every repository call site is already `async def`.
* Exponential backoff with jitter, bounded attempts.
* Lossy by design: after the final attempt we return the caller's chosen
  fallback (False / None / [] etc.) rather than raising — repositories are
  best-effort by contract, the API surface must never crash on a DB hiccup.
* Per-attempt structured log line so /health/sensor and the audit log can
  count failures without parsing free-form messages.
"""

from __future__ import annotations

import asyncio
import functools
import logging
import random
import time
from collections import deque
from typing import Any, Awaitable, Callable, TypeVar

T = TypeVar("T")

log = logging.getLogger("plantvision.retry")


# ---- In-memory retry telemetry --------------------------------------------
# Bounded ring buffer so /health/sensor can report the last N retry events
# without unbounded memory growth. Production deployments should tee this
# to the audit log table (Increment 5) for durable retention.
_RETRY_EVENTS: deque[dict[str, Any]] = deque(maxlen=200)
_RETRY_COUNTERS: dict[str, dict[str, int]] = {}


def _bump(name: str, key: str) -> None:
    bucket = _RETRY_COUNTERS.setdefault(name, {"attempts": 0, "retries": 0, "failures": 0, "successes": 0})
    bucket[key] = bucket.get(key, 0) + 1


def get_retry_stats(name: str | None = None) -> dict[str, Any]:
    """Snapshot of retry counters; used by /health/sensor."""

    if name:
        return dict(_RETRY_COUNTERS.get(name, {}))
    return {n: dict(v) for n, v in _RETRY_COUNTERS.items()}


def get_recent_retry_events(limit: int = 10) -> list[dict[str, Any]]:
    return list(_RETRY_EVENTS)[-limit:]


def reset_retry_telemetry() -> None:
    """Test helper — clears counters and the event ring buffer."""

    _RETRY_EVENTS.clear()
    _RETRY_COUNTERS.clear()
    _VALIDATION_FAILURES.clear()


# ---- Validation-failure ring buffer ---------------------------------------
# Tracked separately from retry telemetry because validation rejections are
# *expected* application events (bad ESP32 firmware sending bad ranges),
# not transient infrastructure failures.

_VALIDATION_FAILURES: deque[float] = deque(maxlen=500)


def record_validation_failure(path: str | None = None) -> None:
    """Append a timestamp for /health/sensor's validation_failures_24h."""

    _VALIDATION_FAILURES.append(time.time())


def count_validation_failures(within_seconds: float = 86400.0) -> int:
    if within_seconds <= 0:
        return 0
    cutoff = time.time() - within_seconds
    return sum(1 for ts in _VALIDATION_FAILURES if ts >= cutoff)


# ---- Decorator ------------------------------------------------------------


def with_retry(
    *,
    name: str,
    attempts: int = 3,
    base_delay: float = 0.15,
    max_delay: float = 2.0,
    fallback: Any = None,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Wrap an async function with bounded exponential-backoff retries.

    Parameters
    ----------
    name : str
        Stable identifier for telemetry (e.g. ``"sensor_repo.insert_reading"``).
    attempts : int
        Maximum attempts (>=1). ``attempts=3`` means 1 initial try + 2 retries.
    base_delay, max_delay : float
        Backoff = ``min(base_delay * 2**i + jitter, max_delay)``.
    fallback : Any
        Value returned when *all* attempts fail. Mirrors each repo's existing
        contract (``False`` for write helpers, ``None`` for ``fetchrow``,
        ``[]`` for list helpers).
    retry_on : tuple[type[BaseException], ...]
        Exception types that count as transient. Anything else is re-raised.
    """

    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exc: BaseException | None = None
            for i in range(attempts):
                _bump(name, "attempts")
                started = time.perf_counter()
                try:
                    result = await fn(*args, **kwargs)
                    if i > 0:
                        _bump(name, "successes")
                        _RETRY_EVENTS.append({
                            "name": name,
                            "outcome": "recovered",
                            "attempt": i + 1,
                            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                            "ts": time.time(),
                        })
                        log.info(
                            "retry recovered name=%s attempt=%d elapsed_ms=%.2f",
                            name, i + 1, (time.perf_counter() - started) * 1000,
                        )
                    return result
                except retry_on as exc:  # noqa: BLE001
                    last_exc = exc
                    is_last = i == attempts - 1
                    if is_last:
                        _bump(name, "failures")
                        _RETRY_EVENTS.append({
                            "name": name,
                            "outcome": "failed",
                            "attempt": i + 1,
                            "error": exc.__class__.__name__,
                            "message": str(exc)[:240],
                            "ts": time.time(),
                        })
                        log.warning(
                            "retry exhausted name=%s attempts=%d error=%s msg=%s",
                            name, i + 1, exc.__class__.__name__, str(exc)[:240],
                        )
                        return fallback  # type: ignore[return-value]

                    _bump(name, "retries")
                    delay = min(base_delay * (2 ** i), max_delay)
                    delay += random.uniform(0, base_delay)  # jitter
                    _RETRY_EVENTS.append({
                        "name": name,
                        "outcome": "retry",
                        "attempt": i + 1,
                        "next_delay_s": round(delay, 3),
                        "error": exc.__class__.__name__,
                        "message": str(exc)[:240],
                        "ts": time.time(),
                    })
                    log.info(
                        "retry scheduled name=%s attempt=%d next_delay_s=%.3f error=%s",
                        name, i + 1, delay, exc.__class__.__name__,
                    )
                    await asyncio.sleep(delay)

            # Unreachable in practice; mypy completeness.
            if last_exc is not None:
                log.warning("retry fell through name=%s error=%s", name, last_exc)
            return fallback  # type: ignore[return-value]

        return wrapper

    return deco
