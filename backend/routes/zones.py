"""CRUD routes for growing zones (Phase 2 persistence)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from schemas.garden_management import (
    DeviceListResponse,
    DeviceOut,
    ZoneIn,
    ZoneListResponse,
    ZoneOut,
)
from services import garden_management

router = APIRouter(prefix="/zones", tags=["zones"])


@router.get("", response_model=ZoneListResponse)
async def list_zones() -> ZoneListResponse:
    source, items = await garden_management.list_zones()
    return ZoneListResponse(source=source, zones=[ZoneOut(**z) for z in items])


@router.post("", response_model=ZoneOut)
async def upsert_zone(payload: ZoneIn) -> ZoneOut:
    saved = await garden_management.upsert_zone(payload.model_dump())
    return ZoneOut(**saved)


@router.put("/{slug}", response_model=ZoneOut)
async def update_zone(slug: str, payload: ZoneIn) -> ZoneOut:
    data = payload.model_dump()
    data["slug"] = slug
    saved = await garden_management.upsert_zone(data)
    return ZoneOut(**saved)


@router.delete("/{slug}")
async def delete_zone(slug: str) -> dict[str, bool]:
    ok = await garden_management.delete_zone(slug)
    if not ok:
        raise HTTPException(status_code=404, detail="Zone not found")
    return {"ok": True}


@router.get("/{slug}/devices", response_model=DeviceListResponse)
async def zone_devices(slug: str) -> DeviceListResponse:
    source, items = await garden_management.list_devices(zone_slug=slug)
    return DeviceListResponse(source=source, devices=[DeviceOut(**d) for d in items])
