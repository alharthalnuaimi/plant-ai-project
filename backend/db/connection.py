"""
Async Postgres connection pool with graceful fallback.

Supports two deployment shapes interchangeably from a single env var:

* Supabase Cloud (recommended for teams):
    DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@<host>.pooler.supabase.com:6543/postgres
  - TLS is mandatory; we auto-enable it when the host matches *.supabase.co.

* Local Postgres / docker-compose (optional):
    DATABASE_URL=postgresql://postgres:<password>@localhost:54322/plantvision
  - No SSL by default; left as-is.

Behavior:
* If `PERSISTENCE_BACKEND=memory` (or asyncpg/Postgres is unavailable),
  `get_pool()` returns `None` and callers fall back to the in-memory
  stores. Nothing crashes if the database is offline.
* On postgres mode we lazily build a single asyncpg pool, shared by
  every repository.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from config.settings import SETTINGS

log = logging.getLogger("plantvision.db")

try:  # asyncpg is optional in `memory` mode
    import asyncpg  # type: ignore
except Exception:  # pragma: no cover - we report later
    asyncpg = None  # type: ignore

_pool: Any | None = None
_init_failed: bool = False


def _is_supabase_cloud(dsn: str) -> bool:
    """Heuristic: Supabase Cloud DSNs use a *.supabase.{co,com} host."""

    try:
        host = (urlparse(dsn).hostname or "").lower()
    except ValueError:
        return False
    return host.endswith(".supabase.co") or host.endswith(".supabase.com")


def deployment_mode() -> str:
    """Best-effort human label for /health/db reporting."""

    if not SETTINGS.use_postgres:
        return "memory"
    if _is_supabase_cloud(SETTINGS.database_url):
        return "cloud"
    return "local"


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

    is_cloud = _is_supabase_cloud(SETTINGS.database_url)
    create_kwargs: dict[str, Any] = {
        "dsn": SETTINGS.database_url,
        "min_size": 1,
        "max_size": 8,
        "command_timeout": 15,
    }
    if is_cloud:
        # Supabase Cloud routes through pgbouncer in transaction-pool mode
        # (Transaction Pooler on port 6543). pgbouncer in transaction mode
        # does NOT support asyncpg's named prepared statement cache, so we
        # disable it. asyncpg falls back to unnamed single-use statements,
        # which pgbouncer handles correctly.
        # Also: TLS is mandatory on Supabase Cloud.
        # Refs: https://magicstack.github.io/asyncpg/current/faq.html#why-am-i-getting-prepared-statement-errors
        create_kwargs["ssl"] = "require"
        create_kwargs["statement_cache_size"] = 0
        # Server-side prepared statements are also disabled; this avoids
        # pgbouncer's "prepared statement does not exist" errors.
        create_kwargs["server_settings"] = {"jit": "off"}

    try:
        _pool = await asyncpg.create_pool(**create_kwargs)
        host = urlparse(SETTINGS.database_url).hostname or SETTINGS.postgres_host
        log.info(
            "Postgres pool ready [%s] host=%s db=%s ssl=%s",
            "cloud" if is_cloud else "local",
            host,
            SETTINGS.postgres_db,
            "on" if is_cloud else "off",
        )
        return _pool
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "Postgres unavailable (%s); falling back to memory store. "
            "Set PERSISTENCE_BACKEND=memory to silence this warning.",
            exc,
        )
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
