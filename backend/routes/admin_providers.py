"""
Admin connected providers endpoints (Phase 8).
Exposes GET /admin/providers and POST /admin/providers/test.
"""

from __future__ import annotations

import io
from typing import Any
from fastapi import APIRouter, HTTPException
from PIL import Image
from pydantic import BaseModel, Field

from services.providers.multi_provider import PROVIDER_REGISTRY

router = APIRouter(prefix="/admin/providers", tags=["admin_providers"])


class TestProviderRequest(BaseModel):
    provider_name: str = Field(description="Name of provider e.g. 'Gemini Vision', 'Roboflow Auto Label'")


@router.get("")
async def list_providers() -> list[dict[str, Any]]:
    """List all supported annotation providers and active connection status."""
    return PROVIDER_REGISTRY.list_providers()


@router.post("/test")
async def test_provider_connection(payload: TestProviderRequest) -> dict[str, Any]:
    """Test connection and return sample annotation from provider."""
    target_name = payload.provider_name.lower().strip()
    provider = next(
        (p for p in PROVIDER_REGISTRY.providers if p.name.lower() == target_name or p.env_var.lower() == target_name),
        None,
    )
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{payload.provider_name}' not found")

    # Providers now receive the image itself, so the connection test must send a real one.
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (40, 110, 60)).save(buf, format="JPEG")
    res = provider.annotate(buf.getvalue(), context_label="Healthy Money Plant")
    return {
        "provider": provider.name,
        "env_var": provider.env_var,
        "active": provider.is_active,
        "test_result": res,
    }
