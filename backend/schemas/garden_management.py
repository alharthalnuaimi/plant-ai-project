"""Schemas for /zones and /devices CRUD."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ZoneIn(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    status: str = Field(default="HEALTHY", max_length=32)
    latitude: float | None = None
    longitude: float | None = None
    plants_count: int = Field(default=0, ge=0)


class ZoneOut(ZoneIn):
    id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ZoneListResponse(BaseModel):
    source: str = "memory"
    zones: list[ZoneOut] = []


class DeviceIn(BaseModel):
    slug: str = Field(min_length=1, max_length=64)
    device_name: str = Field(min_length=1, max_length=128)
    zone_slug: str | None = None
    ip_address: str | None = None
    status: str = Field(default="OFFLINE", max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeviceOut(DeviceIn):
    id: str | None = None
    last_seen: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class DeviceListResponse(BaseModel):
    source: str = "memory"
    devices: list[DeviceOut] = []
