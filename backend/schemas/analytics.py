from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ScanHistoryItem(BaseModel):
    scan_id: str
    user_id: str
    zone_id: str
    disease: str
    confidence: float
    status: Literal["PASS", "WARN", "CRITICAL"]
    inference_ms: float
    timestamp: float
    accepted: bool


class AnalyticsEvent(BaseModel):
    id: str
    timestamp: float
    event_type: Literal["scan", "sensor", "device", "alert", "ai", "system"]
    message: str
    zone_id: str | None = None
    device_id: str | None = None


class ScanOutcomeSlice(BaseModel):
    label: str
    count: int
    pct: float
    tone: Literal["pass", "warn", "crit", "neutral"] = "neutral"


class ZoneHealthSummary(BaseModel):
    zone_id: str
    label: str
    is_demo: bool = False
    air_temperature: float | None = None
    air_humidity: float | None = None
    soil_ph: float | None = None
    soil_ec: float | None = None
    status: Literal["HEALTHY", "WARNING", "CRITICAL"]
    status_note: str = ""
    last_updated: float | None = None
    sparklines: dict[str, list[float]] = Field(default_factory=dict)


class AnalyticsSummary(BaseModel):
    detection_rate: float
    avg_confidence: float
    avg_inference_ms: float
    connected_devices: int
    active_zones: int
    total_scans: int
    scans_today: int
    source: Literal["live", "demo"] = "live"
    top_diseases: list[dict[str, Any]] = Field(default_factory=list)
    activity_by_day: list[dict[str, Any]] = Field(default_factory=list)
    confidence_series: list[float] = Field(default_factory=list)
    scan_outcomes: list[dict[str, Any]] = Field(default_factory=list)
    pass_rate: float = 0.0


class AIInsight(BaseModel):
    insight: str
    recommendation: str
    severity: Literal["info", "warning", "critical"] = "info"


class AnalyticsInsightsResponse(BaseModel):
    items: list[AIInsight]
    source: Literal["live", "demo"] = "live"
