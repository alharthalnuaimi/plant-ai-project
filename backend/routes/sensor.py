from __future__ import annotations

from fastapi import APIRouter

from schemas.contracts import SensorInput

router = APIRouter(tags=["sensor"])

# In-memory last reading for quick mobile demos (replace with SQLite/Firebase later)
_latest: dict | None = None


@router.post("/sensor")
async def sensor(payload: SensorInput) -> dict:
    global _latest
    body = payload.model_dump()
    _latest = body
    return {"ok": True, "stored": body}


@router.get("/sensor/latest")
async def sensor_latest() -> dict:
    if _latest is None:
        return {"stored": None}
    return {"stored": _latest}
