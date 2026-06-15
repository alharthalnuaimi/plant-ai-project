"""Phase 3 — unit tests for ``core.retry``."""

from __future__ import annotations

import pytest

from core.retry import (
    count_validation_failures,
    get_recent_retry_events,
    get_retry_stats,
    record_validation_failure,
    reset_retry_telemetry,
    with_retry,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_state():
    reset_retry_telemetry()
    yield
    reset_retry_telemetry()


@pytest.mark.asyncio
async def test_with_retry_returns_value_on_first_try():
    @with_retry(name="t.fast", attempts=3, fallback=None, base_delay=0.001)
    async def fn() -> str:
        return "ok"

    assert await fn() == "ok"
    stats = get_retry_stats("t.fast")
    assert stats == {"attempts": 1, "retries": 0, "failures": 0, "successes": 0}


@pytest.mark.asyncio
async def test_with_retry_recovers_after_transient_failures():
    state = {"n": 0}

    @with_retry(name="t.recover", attempts=3, fallback="FB", base_delay=0.001)
    async def fn() -> str:
        state["n"] += 1
        if state["n"] < 3:
            raise ConnectionError("blip")
        return "good"

    assert await fn() == "good"
    stats = get_retry_stats("t.recover")
    assert stats["attempts"] == 3
    assert stats["retries"] == 2
    assert stats["successes"] == 1
    events = [e for e in get_recent_retry_events(20) if e.get("name") == "t.recover"]
    assert any(e["outcome"] == "recovered" for e in events)


@pytest.mark.asyncio
async def test_with_retry_returns_fallback_after_exhaustion():
    @with_retry(name="t.fail", attempts=2, fallback="FALLBACK", base_delay=0.001)
    async def fn() -> str:
        raise RuntimeError("boom")

    assert await fn() == "FALLBACK"
    stats = get_retry_stats("t.fail")
    assert stats["failures"] == 1
    failed_events = [
        e for e in get_recent_retry_events(20)
        if e.get("name") == "t.fail" and e.get("outcome") == "failed"
    ]
    assert len(failed_events) == 1


def test_validation_failure_counter_window():
    record_validation_failure("/sensor")
    record_validation_failure("/sensor")
    assert count_validation_failures(within_seconds=86400.0) == 2
    assert count_validation_failures(within_seconds=0.0) == 0


@pytest.mark.asyncio
async def test_with_retry_only_retries_listed_exception_types():
    state = {"n": 0}

    @with_retry(
        name="t.specific",
        attempts=3,
        fallback=None,
        base_delay=0.001,
        retry_on=(ConnectionError,),
    )
    async def fn() -> None:
        state["n"] += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        await fn()

    assert state["n"] == 1
