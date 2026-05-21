"""CRUD routes for ESP32 / sensor devices."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from schemas.garden_management import DeviceIn, DeviceListResponse, DeviceOut
from services import garden_management

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=DeviceListResponse)
async def list_devices(zone: str | None = None) -> DeviceListResponse:
    source, items = await garden_management.list_devices(zone_slug=zone)
    return DeviceListResponse(source=source, devices=[DeviceOut(**d) for d in items])


@router.post("", response_model=DeviceOut)
async def upsert_device(payload: DeviceIn) -> DeviceOut:
    saved = await garden_management.upsert_device(payload.model_dump())
    return DeviceOut(**saved)


@router.put("/{slug}", response_model=DeviceOut)
async def update_device(slug: str, payload: DeviceIn) -> DeviceOut:
    data = payload.model_dump()
    data["slug"] = slug
    saved = await garden_management.upsert_device(data)
    return DeviceOut(**saved)


@router.delete("/{slug}")
async def delete_device(slug: str) -> dict[str, bool]:
    ok = await garden_management.delete_device(slug)
    if not ok:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"ok": True}
