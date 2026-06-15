"""
Phase 4 — Supabase Storage adapter for scan images.

This service is the single seam between the upload pipeline in
`routes/predict.py` and Supabase Storage. It is intentionally narrow:

* No new tables / columns — we still write the resulting object path
  into `scan_results.image_path` (existing column) and a public URL
  into `metadata_json.image_public_url`.
* No new SDKs — we POST to the Supabase Storage REST API via the
  `httpx` client that already ships in `requirements.txt`.
* Failure is always graceful — `upload_scan_image` never raises; the
  predict route falls back to writing under `backend/uploads/` so the
  scan still completes when Storage is offline / misconfigured.

Env contract (see `.env.example` §Scan image storage):

    STORAGE_BACKEND          supabase | local | off   (default: supabase)
    SUPABASE_URL             https://<PROJECT_REF>.supabase.co
    SUPABASE_SERVICE_KEY     service-role key
    SUPABASE_STORAGE_BUCKET  bucket name              (default: scan-images)
"""

from __future__ import annotations

import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

log = logging.getLogger("plantvision.storage")


# ---------------------------------------------------------------- constants

_DEFAULT_BUCKET = "scan-images"
_DEFAULT_BACKEND = "supabase"
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


# ---------------------------------------------------------------- result type


@dataclass(frozen=True)
class StorageUploadResult:
    """Outcome of a single `upload_scan_image` call.

    The caller MUST check ``ok`` before reading ``object_path`` /
    ``public_url``. When ``ok`` is ``False`` the caller is expected to
    fall back to the local `backend/uploads/` path.
    """

    ok: bool
    object_path: str | None = None
    public_url: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "object_path": self.object_path,
            "public_url": self.public_url,
            "error": self.error,
        }


# ---------------------------------------------------------------- env helpers


def _env(name: str, default: str = "") -> str:
    val = os.environ.get(name)
    if val is None:
        return default
    val = val.strip()
    return val if val else default


def _bucket() -> str:
    return _env("SUPABASE_STORAGE_BUCKET", _DEFAULT_BUCKET)


def _backend() -> str:
    return _env("STORAGE_BACKEND", _DEFAULT_BACKEND).lower() or _DEFAULT_BACKEND


def is_enabled() -> bool:
    """Return True when Supabase Storage uploads should be attempted.

    Requires all of:
      * ``SUPABASE_URL`` set
      * ``SUPABASE_SERVICE_KEY`` set
      * ``STORAGE_BACKEND`` is ``supabase`` (default). ``local`` or
        ``off`` force the caller to use the local fallback path.
    """

    backend = _backend()
    if backend != "supabase":
        return False
    url = _env("SUPABASE_URL")
    key = _env("SUPABASE_SERVICE_KEY")
    return bool(url) and bool(key)


# ---------------------------------------------------------------- url helpers


def _strip_trailing_slash(url: str) -> str:
    return url[:-1] if url.endswith("/") else url


def public_url(object_path: str) -> str:
    """Build the public URL for ``object_path`` in the scan-images bucket.

    Shape: ``{SUPABASE_URL}/storage/v1/object/public/{bucket}/{object_path}``.
    Caller is responsible for ensuring the bucket is public; for the
    PlantVision project the operator-verified bucket ``scan-images`` is
    already public.
    """

    base = _strip_trailing_slash(_env("SUPABASE_URL"))
    if not base:
        return object_path
    bucket = _bucket()
    path = object_path.lstrip("/")
    return f"{base}/storage/v1/object/public/{bucket}/{path}"


# ---------------------------------------------------------------- path helpers


def _safe_filename(filename: str) -> str:
    """Strip filesystem-hostile characters from ``filename``.

    Defensive — Supabase Storage accepts most paths but we want
    predictable, ASCII-only object keys so they round-trip cleanly into
    `scan_results.image_path` and the frontend image URL.
    """

    base = (filename or "image").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not base:
        base = "image"
    base = _SAFE_NAME_RE.sub("_", base).strip("._")
    return base or "image"


def _object_path(filename: str) -> str:
    """Build ``scans/YYYY/MM/<uuid>_<safe_name>`` object path."""

    now = datetime.now(timezone.utc)
    safe = _safe_filename(filename)
    return f"scans/{now.year:04d}/{now.month:02d}/{uuid.uuid4().hex}_{safe}"


# ---------------------------------------------------------------- upload


async def upload_scan_image(
    *,
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> StorageUploadResult:
    """Upload ``file_bytes`` to the Supabase Storage scan-images bucket.

    Returns a :class:`StorageUploadResult`. **Never raises** — any
    network / HTTP / parsing error is caught and converted into
    ``ok=False`` so the caller can fall back to the local
    ``backend/uploads/`` write path without a try/except wrapper.
    """

    if not is_enabled():
        return StorageUploadResult(ok=False, error="storage_disabled")

    base = _strip_trailing_slash(_env("SUPABASE_URL"))
    key = _env("SUPABASE_SERVICE_KEY")
    bucket = _bucket()
    object_path = _object_path(filename)
    upload_url = f"{base}/storage/v1/object/{bucket}/{object_path}"
    headers = {
        "Authorization": f"Bearer {key}",
        "apikey": key,
        "Content-Type": content_type or "application/octet-stream",
        # Phase 4 — disable accidental overwrites; the object_path UUID
        # makes collisions effectively impossible anyway.
        "x-upsert": "false",
        "Cache-Control": "public, max-age=31536000, immutable",
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            resp = await client.post(upload_url, content=file_bytes, headers=headers)
    except Exception as exc:  # noqa: BLE001 — never raise from this seam
        log.warning("storage.upload_scan_image network failure: %s", exc)
        return StorageUploadResult(ok=False, error=f"network:{type(exc).__name__}")

    if resp.status_code >= 300:
        # Storage REST returns JSON like {"error":"...","message":"..."}.
        snippet: str
        try:
            body = resp.json()
            snippet = str(body.get("error") or body.get("message") or body)[:200]
        except Exception:  # noqa: BLE001
            snippet = (resp.text or "")[:200]
        log.warning(
            "storage.upload_scan_image rejected status=%s body=%s",
            resp.status_code,
            snippet,
        )
        return StorageUploadResult(ok=False, error=f"http_{resp.status_code}")

    url = public_url(object_path)
    log.info(
        "storage.upload_scan_image ok bucket=%s object=%s bytes=%d",
        bucket,
        object_path,
        len(file_bytes),
    )
    return StorageUploadResult(ok=True, object_path=object_path, public_url=url)


__all__ = [
    "StorageUploadResult",
    "is_enabled",
    "public_url",
    "upload_scan_image",
]
