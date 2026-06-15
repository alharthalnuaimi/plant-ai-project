"""
Audit log service (Phase 3, Increment 5).

Public surface:

    log_event(...)          – fire-and-forget: schedules an async write.
    log_event_sync(...)     – the same payload from sync code (uses
                              asyncio.run_coroutine_threadsafe under the
                              event loop).
    list_recent(...)        – read-side helper for /health/sensor and
                              future ops dashboards.

Design:

* All writes are non-blocking — the audit table must never delay user
  requests. Failures are caught and dropped; ``recent_in_memory()``
  returns the last 200 events from a ring buffer so even when
  Supabase is down, ``/health/sensor`` still has *something* to show.
* `log_retry_event` / `log_validation_event` / `log_request_event` are
  thin wrappers so callers don't have to remember the right
  ``event_type`` / ``severity`` strings.
* The service mirrors ``core.retry``'s in-memory ring buffer pattern.
  When you want a durable record, also call ``log_event``.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any

from config.settings import SETTINGS
from repositories import audit_repo

log = logging.getLogger("plantvision.audit")


# ---- In-memory ring buffer (always populated, even when DB down) ----------

_AUDIT_RING: deque[dict[str, Any]] = deque(maxlen=200)


def _record_in_memory(payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload.setdefault("ts", time.time())
    _AUDIT_RING.append(payload)


def recent_in_memory(limit: int = 50) -> list[dict[str, Any]]:
    return list(_AUDIT_RING)[-limit:]


def reset_in_memory() -> None:
    """Test helper."""

    _AUDIT_RING.clear()


# ---- Async write path -----------------------------------------------------


async def log_event(
    *,
    event_type: str,
    severity: str = "info",
    operation: str | None = None,
    request_id: str | None = None,
    actor: str | None = None,
    zone_slug: str | None = None,
    device_slug: str | None = None,
    plant_id: str | None = None,
    outcome: str | None = None,
    elapsed_ms: float | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> bool:
    """Persist one audit row. Returns True on success, False otherwise.

    Always populates the in-memory ring buffer regardless of DB outcome.
    """

    record = {
        "event_type": event_type,
        "severity": severity,
        "operation": operation,
        "request_id": request_id,
        "actor": actor,
        "zone_slug": zone_slug,
        "device_slug": device_slug,
        "plant_id": plant_id,
        "outcome": outcome,
        "elapsed_ms": elapsed_ms,
        "error_class": error_class,
        "error_message": error_message,
        "payload": payload or {},
    }
    _record_in_memory(record)

    if not SETTINGS.use_postgres:
        return False

    try:
        return await audit_repo.insert_audit(**record)
    except Exception as exc:  # noqa: BLE001 — audit must never crash callers
        log.warning("audit insert failed (non-fatal): %s", exc)
        return False


def log_event_nowait(**kwargs: Any) -> None:
    """Fire-and-forget audit log from inside an async context.

    Schedules the coroutine on the running event loop and returns
    immediately. If no loop is running (e.g. one-off scripts), falls
    back to in-memory only.
    """

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(log_event(**kwargs))
    except RuntimeError:
        # No event loop: just buffer in memory.
        _record_in_memory(kwargs)


# ---- Convenience wrappers --------------------------------------------------


def log_retry_event(
    *,
    operation: str,
    outcome: str,
    attempt: int,
    elapsed_ms: float | None = None,
    error_class: str | None = None,
    error_message: str | None = None,
    request_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    severity = {
        "recovered": "info",
        "retry": "warning",
        "failed": "error",
    }.get(outcome, "info")
    log_event_nowait(
        event_type="retry",
        severity=severity,
        operation=operation,
        outcome=outcome,
        elapsed_ms=elapsed_ms,
        error_class=error_class,
        error_message=error_message,
        request_id=request_id,
        payload={**(payload or {}), "attempt": attempt},
    )


def log_validation_event(
    *,
    route: str,
    request_id: str | None,
    actor: str | None,
    payload: dict[str, Any],
) -> None:
    log_event_nowait(
        event_type="sensor_validation_failed" if route == "/sensor" else "validation_failed",
        severity="warning",
        operation=route,
        request_id=request_id,
        actor=actor,
        outcome="rejected",
        payload=payload,
    )


def log_request_event(
    *,
    route: str,
    request_id: str | None,
    actor: str | None = None,
    zone_slug: str | None = None,
    device_slug: str | None = None,
    plant_id: str | None = None,
    outcome: str = "success",
    elapsed_ms: float | None = None,
    severity: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    """Audit a notable request — /predict, /report, /care/{plant}.

    Caller decides ``severity`` (defaults: success → info, error → error).
    """

    if severity is None:
        severity = "info" if outcome == "success" else "error"
    log_event_nowait(
        event_type=_route_event_type(route),
        severity=severity,
        operation=route,
        request_id=request_id,
        actor=actor,
        zone_slug=zone_slug,
        device_slug=device_slug,
        plant_id=plant_id,
        outcome=outcome,
        elapsed_ms=elapsed_ms,
        payload=payload or {},
    )


def _route_event_type(route: str) -> str:
    if route.startswith("/predict"):
        return "predict"
    if route.startswith("/report"):
        return "report"
    if route.startswith("/care"):
        return "care"
    return "request"


# ---- Read-side -------------------------------------------------------------


async def list_recent(
    *,
    limit: int = 50,
    event_type: str | None = None,
    severity: str | None = None,
) -> list[dict[str, Any]]:
    """Return recent audit rows from the DB; falls back to memory ring."""

    if not SETTINGS.use_postgres:
        return recent_in_memory(limit)
    try:
        rows = await audit_repo.recent_audit(
            limit=limit, event_type=event_type, severity=severity
        )
        if rows:
            return rows
    except Exception as exc:  # noqa: BLE001
        log.warning("audit recent fetch failed: %s", exc)
    return recent_in_memory(limit)
