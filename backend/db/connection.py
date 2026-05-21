"""
Async Postgres connection pool with graceful fallback.

* If `PERSISTENCE_BACKEND=memory` (or asyncpg/Postgres is unavailable),
  `get_pool()` returns `None` and callers fall back to the in-memory
  stores. Nothing crashes if the database is offline.
* On postgres mode we lazily build a single asyncpg pool. The pool is
  shared across all repositories.
"""

from __future__ import annotations

import logging
from typing import Any

from config.settings import SETTINGS

log = logging.getLogger("plantvision.db")

try:  # asyncpg is optional in `memory` mode
    import asyncpg  # type: ignore
except Exception:  # pragma: no cover - we report later
    asyncpg = None  # type: ignore

_pool: Any | None = None
_init_failed: bool = False


def is_postgres_enabled() -> bool:
    """True if the backend should attempt to use Postgres at all."""

    return SETTINGS.use_postgres and asyncpg is not None and not _init_failed


async def get_pool() -> Any | None:
    """Return the shared asyncpg pool, or None if persistence is disabled."""

    global _pool, _init_failed

    if not SETTINGS.use_postgres:
        return None
    if asyncpg is None:
        log.warning(
            "PERSISTENCE_BACKEND=postgres but asyncpg is not installed; "
            "falling back to memory store. Install with: pip install asyncpg"
        )
        _init_failed = True
        return None
    if _init_failed:
        return None
    if _pool is not None:
        return _pool

    try:
        _pool = await asyncpg.create_pool(
            dsn=SETTINGS.database_url,
            min_size=1,
            max_size=8,
            command_timeout=10,
        )
        log.info("Postgres pool ready (%s:%s/%s)", SETTINGS.postgres_host,
                 SETTINGS.postgres_port, SETTINGS.postgres_db)
        return _pool
    except Exception as exc:  # noqa: BLE001
        log.warning("Postgres unavailable (%s); using memory store.", exc)
        _init_failed = True
        return None


async def close_pool() -> None:
    """Gracefully close the pool on shutdown."""

    global _pool
    if _pool is None:
        return
    try:
        await _pool.close()
    finally:
        _pool = None


async def ping() -> bool:
    """Return True if a SELECT 1 round-trip succeeds."""

    pool = await get_pool()
    if pool is None:
        return False
    try:
        async with pool.acquire() as conn:
            val = await conn.fetchval("select 1")
            return val == 1
    except Exception:
        return False
