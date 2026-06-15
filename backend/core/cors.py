"""
CORS origin allowlist helpers (Phase 4).

The MVP shipped with ``allow_origins=["*"]`` because every developer
deployment (Vercel preview URLs, local Node static server, the
DevContainer port-forward, etc.) needed to reach the FastAPI backend
without any extra config. That's fine for a demo, but production
deployments should pin the allowlist to known frontend domains.

This module exposes two tiny helpers used by ``backend/main.py``:

* :func:`parse_cors_origins` — turn a comma-separated env value into the
  ``list[str]`` that :class:`CORSMiddleware` expects, while preserving
  the legacy wide-open default when the variable is missing/empty/``*``.
* :func:`resolved_cors_origins` — read ``CORS_ALLOWED_ORIGINS`` from the
  environment and feed it through the parser. Pulled out so the wiring
  in ``main.py`` stays a one-liner and is straightforward to unit-test.

Design notes
------------
* The function is intentionally permissive: any error path collapses to
  ``["*"]`` rather than dropping CORS entirely (which would break the
  frontend without any visible signal).
* Order is preserved so operators can put their highest-traffic origin
  first in the env value if they ever want to reason about hit-rate.
* No external dependencies — keeps the test suite zero-cost.
"""

from __future__ import annotations

import os
from typing import Iterable

WILDCARD: list[str] = ["*"]


def parse_cors_origins(value: str | None) -> list[str]:
    """Parse a comma-separated CORS origin list.

    Returns ``["*"]`` when:
      * ``value`` is ``None`` or empty / whitespace-only,
      * ``value`` (trimmed) equals ``"*"``,
      * after splitting + stripping + de-duping, nothing usable remains.

    Otherwise returns the parsed origins, preserving input order and
    dropping empty / duplicate entries.
    """

    if value is None:
        return list(WILDCARD)

    trimmed = value.strip()
    if not trimmed or trimmed == "*":
        return list(WILDCARD)

    seen: set[str] = set()
    out: list[str] = []
    for chunk in _split_commas(trimmed):
        origin = chunk.strip()
        if not origin or origin in seen:
            continue
        seen.add(origin)
        out.append(origin)

    return out or list(WILDCARD)


def resolved_cors_origins(env: dict[str, str] | None = None) -> list[str]:
    """Read ``CORS_ALLOWED_ORIGINS`` (defaulting to :data:`os.environ`).

    A separate function so tests can inject a fake env without monkey-
    patching ``os.environ``.
    """

    src = env if env is not None else os.environ
    return parse_cors_origins(src.get("CORS_ALLOWED_ORIGINS"))


def _split_commas(value: str) -> Iterable[str]:
    """Yield comma-separated chunks, tolerant of trailing commas."""

    for chunk in value.split(","):
        yield chunk
