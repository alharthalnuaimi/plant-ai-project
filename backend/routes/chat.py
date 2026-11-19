"""POST /chat — Gemini reasoning over a scan, live sensor context and the user's question.

There is no rule-based fallback narrative: if Gemini is unavailable the
route returns a structured error (``{"error": "gemini_*", "message": ...}``)
and the client can retry.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError, model_validator

from schemas.contracts import SurvivalResponse, VisionResult
from services import analytics_store, sensor_store
from services.gemini.schemas import GeminiDiagnosis
from services.gemini.reasoning import build_reasoning_context, reason_about_plant
from services.survival import SurvivalInputs, compute_survival

router = APIRouter(tags=["chat"])

log = logging.getLogger("plantvision.chat")


class ChatSensors(BaseModel):
    """Sensor context. Every field is optional: a missing value means "no data"."""

    # Legacy names (kept so existing clients keep working).
    soil_moisture: float | None = Field(default=None, ge=0, le=100, description="Soil moisture %")
    temperature: float | None = Field(default=None, description="Air temperature °C")
    humidity: float | None = Field(default=None, ge=0, le=100, description="Air humidity %")
    species: str | None = Field(default=None, max_length=100)
    # Full ESP32 sensor set.
    soil_temperature: float | None = Field(default=None, description="Soil temperature °C")
    soil_ph: float | None = Field(default=None, ge=0, le=14)
    soil_ec: float | None = Field(default=None, ge=0, description="Soil EC mS/cm")
    light_lux: float | None = Field(default=None, ge=0)
    timestamp: str | None = Field(default=None, description="ISO time the readings were taken")


class ChatRequest(BaseModel):
    vision: VisionResult | None = None
    sensors: ChatSensors = Field(default_factory=ChatSensors)
    user_question: str | None = Field(default=None, max_length=2000)
    # Optional: lets the backend pull the newest stored reading for this device.
    user_id: str | None = None
    zone_id: str | None = None
    device_id: str | None = None
    # UI language: "en" (default) or "ar" — Gemini answers in that language.
    language: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def _needs_something_to_reason_about(self) -> "ChatRequest":
        if self.vision is None and not (self.user_question or "").strip():
            raise ValueError("Provide a scan result (vision) or a user_question.")
        return self


# The client sends this back from an earlier /predict, so accept it only in the
# shape /predict produces and at a sane size.
_MAX_DIAGNOSIS_CHARS = 20_000
# Upper bound on everything sent to Gemini for one chat turn.
_MAX_CONTEXT_CHARS = 60_000


def _checked_diagnosis(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    try:
        diagnosis = GeminiDiagnosis.model_validate(raw).model_dump()
    except ValidationError:
        log.info("POST /chat — ignoring a gemini_diagnosis that doesn't match the schema")
        return None
    if len(json.dumps(diagnosis, default=str)) > _MAX_DIAGNOSIS_CHARS:
        log.info("POST /chat — ignoring an oversized gemini_diagnosis")
        return None
    return diagnosis


def _recent_scan_summaries(limit: int = 5) -> list[dict[str, Any]]:
    """Newest scans, reduced to a compact summary. Returns [] on any error."""

    try:
        rows = analytics_store.get_history(limit=limit)
    except Exception as exc:  # noqa: BLE001 — never block the chat route
        log.debug("scan history enrichment skipped: %s", exc)
        return []
    return [
        {
            "scan_id": r.scan_id,
            "zone_id": r.zone_id,
            "disease": r.disease,
            "confidence": round(float(r.confidence), 4),
            "status": r.status,
            "timestamp": r.timestamp,
        }
        for r in rows
    ]


def _sensor_values(req: ChatRequest) -> dict[str, Any]:
    """Prefer the newest stored device reading; otherwise use what the client sent."""

    if req.zone_id or req.device_id or req.user_id:
        try:
            latest = sensor_store.get_latest(
                user_id=(req.user_id or sensor_store.DEFAULT_USER_ID),
                zone_id=(req.zone_id or sensor_store.DEFAULT_ZONE_ID),
                device_id=(req.device_id or sensor_store.DEFAULT_DEVICE_ID),
            )
        except Exception:  # noqa: BLE001
            latest = None
        if latest is not None:
            return {
                "air_temperature": latest.air_temperature,
                "air_humidity": latest.air_humidity,
                "soil_temperature": latest.soil_temperature,
                "soil_humidity": latest.soil_humidity,
                "soil_ph": latest.soil_ph,
                "soil_ec": latest.soil_ec,
                "light_lux": latest.light_lux,
                "timestamp": latest.timestamp,
                "source": "device",
            }

    s = req.sensors
    return {
        "air_temperature": s.temperature,
        "air_humidity": s.humidity,
        "soil_temperature": s.soil_temperature,
        "soil_humidity": s.soil_moisture,
        "soil_ph": s.soil_ph,
        "soil_ec": s.soil_ec,
        "light_lux": s.light_lux,
        "timestamp": s.timestamp,
        "source": "client",
    }


def _survival(vision: VisionResult | None, values: dict[str, Any], species: str | None) -> SurvivalResponse | None:
    """Rule-based score, only when the inputs it needs actually exist."""

    needed = (values.get("soil_humidity"), values.get("air_temperature"), values.get("air_humidity"))
    if vision is None or any(v is None for v in needed):
        return None
    return SurvivalResponse.model_validate(
        compute_survival(
            SurvivalInputs(
                disease=vision.disease,
                disease_confidence=vision.confidence,
                stress_hint=vision.stress_hint,
                soil_moisture=float(values["soil_humidity"]),
                temperature_c=float(values["air_temperature"]),
                humidity_pct=float(values["air_humidity"]),
                species=species,
            )
        )
    )


@router.post("/chat")
async def chat(req: ChatRequest) -> dict:
    values = _sensor_values(req)
    species = req.sensors.species or (
        req.vision.plant.common_name if req.vision and req.vision.plant else None
    )
    survival = _survival(req.vision, values, species)

    vision_summary = None
    diagnosis = None
    if req.vision is not None:
        meta = req.vision.metadata or {}
        diagnosis = _checked_diagnosis(meta.get("gemini_diagnosis"))
        vision_summary = {
            "label": meta.get("raw_disease_label") or req.vision.disease,
            "confidence": req.vision.confidence,
            "accepted": req.vision.accepted,
            "stress_hint": req.vision.stress_hint,
            "species": species,
            "plant": req.vision.plant.model_dump() if req.vision.plant else None,
        }

    context = build_reasoning_context(
        diagnosis=diagnosis,
        vision_summary=vision_summary,
        sensors=values,
        survival=survival.model_dump() if survival else None,
        history=_recent_scan_summaries(limit=5),
        user_question=req.user_question,
    )

    if len(json.dumps(context, default=str)) > _MAX_CONTEXT_CHARS:
        raise HTTPException(status_code=413, detail="Request is too large to analyse")

    outcome = await run_in_threadpool(reason_about_plant, context, language=req.language)
    log.info("POST /chat — Gemini reasoning ok model=%s", outcome.model)

    return {
        "recommendation": outcome.primary_recommendation(),
        "reply": outcome.reply_text(),
        "source": "gemini",
        "model": outcome.model,
        "reasoning": outcome.reasoning.model_dump(),
        "sensor_context": {"source": values.get("source"), "timestamp": values.get("timestamp")},
        "survival_probability": survival.survival_probability if survival else None,
        "breakdown": survival.breakdown.model_dump() if survival else None,
    }
