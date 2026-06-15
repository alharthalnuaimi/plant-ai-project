"""
Unified AI Plant Report (Phase 3) — POST /report.

Two request shapes, one response shape:

* ``multipart/form-data`` with an image — full image-driven analysis,
  identical underlying pipeline as ``/predict`` but with the unified
  ``PlantReport`` envelope.
* ``application/json`` body — hydrate a report from the most recent
  persisted scan + live sensor cache (no image required). Useful for
  AI-assistant queries and dashboard refreshes.

The endpoint never persists anything new — it's a synthesis endpoint
over services that already own their writes (predict.py persists scans;
sensor.py persists readings).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from schemas.report import PlantReport, ReportRequest
from services.config_loader import get_runtime_config
from services.report_builder import (
    build_report_from_image,
    build_report_from_plant_id,
)

log = logging.getLogger("plantvision.report.route")

router = APIRouter(tags=["report"])


def _min_image_bytes() -> int:
    return int(
        get_runtime_config()
        .get("thresholds", {})
        .get("prediction", {})
        .get("min_image_bytes", 32)
    )


@router.post("/report", response_model=PlantReport)
async def report(
    request: Request,
    # Multipart fields (all optional so the JSON path is reachable).
    file: UploadFile | None = File(default=None),
    user_id: str = Form(default="demo_user"),
    zone_id: str = Form(default="zone_alpha"),
    device_id: str = Form(default="esp32_001"),
    plant_id: str = Form(default=""),
    species_id: str = Form(default=""),
    identify: bool = Form(default=True),
) -> PlantReport:
    """Build a unified plant report.

    * If ``file`` is supplied → run the image pipeline.
    * Otherwise expect a JSON body matching :class:`ReportRequest`.
    """

    content_type = (request.headers.get("content-type") or "").lower()

    # ---- Image path ------------------------------------------------------
    if file is not None and getattr(file, "filename", None):
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Expected an image upload")

        data = await file.read()
        if len(data) < _min_image_bytes():
            raise HTTPException(status_code=400, detail="Image too small or empty")

        try:
            return build_report_from_image(
                data,
                user_id=(user_id or "demo_user").strip() or "demo_user",
                zone_id=(zone_id or "zone_alpha").strip() or "zone_alpha",
                device_id=(device_id or "esp32_001").strip() or "esp32_001",
                plant_id=(plant_id or "").strip() or None,
                species_id=(species_id or "").strip() or None,
                identify=bool(identify),
            )
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            log.exception("/report image path failed")
            raise HTTPException(
                status_code=503,
                detail=f"Report builder failed: {type(exc).__name__}",
            ) from exc

    # ---- JSON path -------------------------------------------------------
    if "application/json" not in content_type:
        raise HTTPException(
            status_code=400,
            detail="Provide either an image upload (multipart) or a JSON body with plant_id.",
        )

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    payload = ReportRequest.model_validate(body or {})

    try:
        return build_report_from_plant_id(
            plant_id=(payload.plant_id or "").strip() or None,
            user_id=(payload.user_id or "demo_user").strip() or "demo_user",
            zone_id=(payload.zone_id or "zone_alpha").strip() or "zone_alpha",
            device_id=(payload.device_id or "esp32_001").strip() or "esp32_001",
            species_id=(payload.species_id or "").strip() or None,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("/report json path failed")
        raise HTTPException(
            status_code=503,
            detail=f"Report builder failed: {type(exc).__name__}",
        ) from exc
