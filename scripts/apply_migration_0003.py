"""Apply migration 0003_audit_log.sql against the configured database.

Idempotent — safe to run multiple times.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Make `backend` importable when running from repo root
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from db.connection import get_pool  # noqa: E402


async def main() -> int:
    pool = await get_pool()
    if pool is None:
        print("No pool available; cannot apply migration.")
        return 1

    sql_path = ROOT / "supabase" / "migrations" / "0003_audit_log.sql"
    sql = sql_path.read_text(encoding="utf-8")

    async with pool.acquire() as conn:
        await conn.execute(sql)
        count = await conn.fetchval("select count(*) from public.audit_log")
        cols = await conn.fetch(
            """
            select column_name
            from information_schema.columns
            where table_schema='public' and table_name='audit_log'
            order by ordinal_position
            """
        )
        idx = await conn.fetch(
            """
            select indexname
            from pg_indexes
            where schemaname='public' and tablename='audit_log'
            order by indexname
            """
        )

    print(f"audit_log row count = {count}")
    print(f"audit_log columns   = {[r['column_name'] for r in cols]}")
    print(f"audit_log indexes   = {[r['indexname'] for r in idx]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
