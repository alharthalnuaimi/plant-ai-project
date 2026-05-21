"""
Database access layer.

Importing this package does NOT open a connection. Call
`from db.connection import get_pool` (or `get_pool_blocking`) on demand.
"""

from .connection import (
    close_pool,
    get_pool,
    is_postgres_enabled,
    ping,
)

__all__ = ["close_pool", "get_pool", "is_postgres_enabled", "ping"]
