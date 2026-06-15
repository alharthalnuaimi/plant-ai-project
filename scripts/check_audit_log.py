"""Quick visibility of public.audit_log — used after running migration 0003."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from db.connection import get_pool  # noqa: E402


async def main() -> int:
    pool = await get_pool()
    if pool is None:
        print("No pool available.")
        return 1

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            select event_type, severity, operation, outcome, actor,
                   created_at
            from public.audit_log
            order by created_at desc
            limit 5
            """
        )
        total = await conn.fetchval("select count(*) from public.audit_log")

    print(f"audit_log total rows = {total}")
    for r in rows:
        print(
            f"  [{r['created_at'].isoformat()}] "
            f"{r['event_type']}/{r['severity']} "
            f"op={r['operation']} outcome={r['outcome']} actor={r['actor']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
