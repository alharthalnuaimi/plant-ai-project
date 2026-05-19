from __future__ import annotations

from fastapi import APIRouter, Query

from schemas.health import PlantHealthScore
from services import analytics_store, sensor_store
from services.plant_health import compute_plant_health

router = APIRouter(tags=["health"])


@router.get("/health/plant", response_model=PlantHealthScore)
async def plant_health(
    user_id: str = Query(default="demo_user"),
    zone_id: str = Query(default="zone_alpha"),
    device_id: str = Query(default="esp32_001"),
) -> PlantHealthScore:
    uid = (user_id or "demo_user").strip() or "demo_user"
    zid = (zone_id or "zone_alpha").strip() or "zone_alpha"
    did = (device_id or "esp32_001").strip() or "esp32_001"

    scan = analytics_store.get_latest_scan(user_id=uid, zone_id=zid)
    sensor = sensor_store.get_latest(uid, zid, did)

    if scan:
        from services.plant_health import compute_from_scan_record

        return compute_from_scan_record(scan, sensor)

    if sensor:
        return compute_plant_health(
            "healthy",
            0.5,
            accepted=True,
            sensor=sensor,
            source="demo" if getattr(sensor, "is_demo", False) else "live",
        )

    return compute_plant_health(
        "healthy",
        0.0,
        accepted=False,
        sensor=None,
        source="baseline",
    )
