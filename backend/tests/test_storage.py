"""
Phase 4 — Supabase Storage adapter tests.

Fully isolated:
* No real network — `httpx.AsyncClient.post` is monkeypatched to a
  fake awaitable that returns a stubbed `httpx.Response`.
* No real Supabase — env vars are set/cleared with `monkeypatch`.
* No real disk for the success path — the predict-route test relies on
  the storage stub, the local fallback path writes under
  `backend/uploads/` which is already a tracked working directory.

Covers the four required scenarios:
  1. upload success → returns object_path + public_url, image lands at
     `scans/YYYY/MM/<uuid>_<filename>` in the requested bucket.
  2. upload failure (HTTP 500) → returns `ok=False` instead of raising.
  3. storage disabled (`STORAGE_BACKEND=off`, or missing env vars) →
     short-circuits to `ok=False, error="storage_disabled"`.
  4. scan-history surface resolves the public URL for rows persisted
     via Storage, both via `metadata.image_public_url` and via an
     image_path that looks like a Storage object key.

Plus one bonus end-to-end check that wires the FastAPI `/predict`
route through a monkeypatched storage adapter and asserts the metadata
carries the Supabase public URL (no real upload happens).
"""

from __future__ import annotations

import io
import re
from typing import Any

import httpx
import pytest
from PIL import Image

from routes import scans as scans_route
from services import storage


pytestmark = pytest.mark.smoke


# ---------------------------------------------------------------- helpers


def _set_supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "test-service-key")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", "scan-images")


def _clear_supabase_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_STORAGE_BUCKET", raising=False)


class _FakeAsyncClient:
    """Minimal stand-in for ``httpx.AsyncClient`` used by the adapter."""

    def __init__(self, *, response: httpx.Response | None = None, exc: Exception | None = None) -> None:
        self._response = response
        self._exc = exc
        self.posts: list[dict[str, Any]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def post(self, url: str, *, content: bytes, headers: dict[str, str]) -> httpx.Response:
        self.posts.append({"url": url, "content": content, "headers": dict(headers)})
        if self._exc is not None:
            raise self._exc
        assert self._response is not None
        return self._response


def _install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response: httpx.Response | None = None,
    exc: Exception | None = None,
) -> _FakeAsyncClient:
    """Patch ``services.storage.httpx.AsyncClient`` to return ``client``.

    Returns the same fake instance so the test can inspect the captured
    POST(s).
    """

    client = _FakeAsyncClient(response=response, exc=exc)

    def _factory(*_args: Any, **_kwargs: Any) -> _FakeAsyncClient:
        return client

    monkeypatch.setattr(storage.httpx, "AsyncClient", _factory)
    return client


# ---------------------------------------------------------------- tests


@pytest.mark.asyncio
async def test_upload_success_returns_object_path_and_public_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_supabase_env(monkeypatch)
    response = httpx.Response(200, json={"Key": "scan-images/whatever"})
    fake = _install_fake_client(monkeypatch, response=response)

    result = await storage.upload_scan_image(
        file_bytes=b"\x89PNG fake bytes",
        filename="my leaf!.JPG",
        content_type="image/jpeg",
    )

    assert result.ok is True
    assert result.error is None
    assert result.object_path is not None
    assert re.fullmatch(
        r"scans/\d{4}/\d{2}/[a-f0-9]{32}_my_leaf_.JPG",
        result.object_path,
    ), f"unexpected object_path={result.object_path!r}"
    assert result.public_url == (
        "https://example.supabase.co/storage/v1/object/public/scan-images/"
        + result.object_path
    )

    assert len(fake.posts) == 1
    sent = fake.posts[0]
    assert sent["url"] == (
        "https://example.supabase.co/storage/v1/object/scan-images/"
        + result.object_path
    )
    assert sent["headers"]["Authorization"] == "Bearer test-service-key"
    assert sent["headers"]["apikey"] == "test-service-key"
    assert sent["headers"]["Content-Type"] == "image/jpeg"


@pytest.mark.asyncio
async def test_upload_failure_returns_ok_false(monkeypatch: pytest.MonkeyPatch) -> None:
    _set_supabase_env(monkeypatch)
    response = httpx.Response(500, json={"error": "Internal Server Error"})
    _install_fake_client(monkeypatch, response=response)

    result = await storage.upload_scan_image(
        file_bytes=b"x" * 256,
        filename="leaf.jpg",
        content_type="image/jpeg",
    )

    assert result.ok is False
    assert result.object_path is None
    assert result.public_url is None
    assert result.error == "http_500"


@pytest.mark.asyncio
async def test_upload_network_failure_returns_ok_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A transport-level exception must NOT bubble out of the adapter."""

    _set_supabase_env(monkeypatch)
    _install_fake_client(monkeypatch, exc=httpx.ConnectError("boom"))

    result = await storage.upload_scan_image(
        file_bytes=b"x" * 256,
        filename="leaf.jpg",
        content_type="image/jpeg",
    )

    assert result.ok is False
    assert result.error == "network:ConnectError"


@pytest.mark.asyncio
async def test_storage_disabled_returns_not_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Case 1: explicit off switch
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "off")
    assert storage.is_enabled() is False
    result = await storage.upload_scan_image(
        file_bytes=b"x" * 256, filename="a.jpg", content_type="image/jpeg"
    )
    assert result.ok is False
    assert result.error == "storage_disabled"

    # Case 2: STORAGE_BACKEND=supabase but env keys missing
    _clear_supabase_env(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    assert storage.is_enabled() is False

    # Case 3: env keys present but backend forced local
    _set_supabase_env(monkeypatch)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    assert storage.is_enabled() is False


def test_scan_history_resolves_storage_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rows persisted via Storage must surface the Supabase public URL."""

    _set_supabase_env(monkeypatch)

    # Case A — metadata.image_public_url wins.
    public_url = "https://example.supabase.co/storage/v1/object/public/scan-images/scans/2026/06/abc_leaf.jpg"
    row = {
        "id": "11111111-1111-1111-1111-111111111111",
        "user_slug": "demo_user",
        "zone_slug": "zone_alpha",
        "device_slug": "esp32_001",
        "image_path": "scans/2026/06/abc_leaf.jpg",
        "disease": "Healthy",
        "confidence": 0.93,
        "accepted": True,
        "metadata_json": {
            "image_public_url": public_url,
            "scan_source": "upload",
        },
        "created_at": "2026-06-04T10:00:00+00:00",
    }
    item = scans_route._row_to_item(row)
    assert item.image_path == "scans/2026/06/abc_leaf.jpg"
    assert item.image_url == public_url

    # Case B — only image_path is set; helper must derive the public URL.
    row_b = dict(row)
    row_b["metadata_json"] = {"scan_source": "upload"}
    item_b = scans_route._row_to_item(row_b)
    assert item_b.image_path == "scans/2026/06/abc_leaf.jpg"
    assert item_b.image_url == (
        "https://example.supabase.co/storage/v1/object/public/scan-images/scans/2026/06/abc_leaf.jpg"
    )

    # Case C — legacy local path keeps the /uploads/<file> shape.
    row_c = dict(row)
    row_c["image_path"] = "uploads/abc.jpg"
    row_c["metadata_json"] = {"image_url": "/uploads/abc.jpg"}
    item_c = scans_route._row_to_item(row_c)
    assert item_c.image_path == "uploads/abc.jpg"
    assert item_c.image_url == "/uploads/abc.jpg"


# ---------------------------------------------------------------- end-to-end


def _tiny_jpeg() -> bytes:
    img = Image.new("RGB", (96, 96), color=(40, 110, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


def test_predict_route_uses_storage_object_path_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    fastapi_client: Any,
) -> None:
    """FastAPI /predict integration — when Storage is enabled and the
    upload succeeds, the response's metadata must carry the Supabase
    public URL and `saved_path` (which becomes `image_path` downstream)
    must be the object key, NOT a local `uploads/<uuid>` path."""

    _set_supabase_env(monkeypatch)

    object_path = "scans/2026/06/deadbeef_leaf.jpg"
    public_url = (
        "https://example.supabase.co/storage/v1/object/public/scan-images/"
        + object_path
    )

    async def fake_upload(
        *, file_bytes: bytes, filename: str, content_type: str
    ) -> storage.StorageUploadResult:
        return storage.StorageUploadResult(
            ok=True,
            object_path=object_path,
            public_url=public_url,
        )

    # Patch at the predict-route import-site too, since `routes.predict`
    # does `from services import storage` (module attribute lookup).
    monkeypatch.setattr(storage, "upload_scan_image", fake_upload)
    monkeypatch.setattr(storage, "is_enabled", lambda: True)

    files = {"file": ("leaf.jpg", _tiny_jpeg(), "image/jpeg")}
    data = {"user_id": "demo_user", "zone_id": "zone_alpha"}
    r = fastapi_client.post("/predict", files=files, data=data)
    assert r.status_code == 200, r.text

    body = r.json()
    assert body["metadata"]["saved_path"] == object_path
    assert body["metadata"]["image_url"] == public_url
    assert body["metadata"]["image_public_url"] == public_url
