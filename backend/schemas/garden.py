"""Garden map dashboard API models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from schemas.analytics import AnalyticsEvent


class GardenInsight(BaseModel):
    label: str
    tone: Literal["pass", "warn", "crit"] = "pass"


class GardenDevice(BaseModel):
    device_id: str
    zone_id: str
    user_id: str
    status: Literal["HEALTHY", "WARNING", "CRITICAL", "OFFLINE"] = "OFFLINE"
    freshness: Literal["live", "stale", "offline"] = "offline"
    last_updated: float | None = None
    air_temperature: float | None = None
    air_humidity: float | None = None
    light_lux: float | None = None
    soil_temperature: float | None = None
    soil_humidity: float | None = None
    soil_ph: float | None = None
    soil_ec: float | None = None
    insights: list[GardenInsight] = Field(default_factory=list)
    sparklines: dict[str, list[float]] = Field(default_factory=dict)


class GardenZone(BaseModel):
    zone_id: str
    label: str
    status: Literal["HEALTHY", "WARNING", "CRITICAL", "OFFLINE"] = "OFFLINE"
    status_note: str = ""
    device_count: int = 0
    last_updated: float | None = None
    air_temperature: float | None = None
    air_humidity: float | None = None
    soil_ph: float | None = None
    soil_ec: float | None = None


class GardenSummary(BaseModel):
    healthy: int = 0
    warning: int = 0
    critical: int = 0
    offline_devices: int = 0


class GardenActivityItem(BaseModel):
    timestamp: float
    message: str
    zone_id: str | None = None
    device_id: str | None = None
    severity: Literal["info", "warn", "crit"] = "info"


class GardenDashboard(BaseModel):
    source: Literal["live", "demo"] = "demo"
    summary: GardenSummary
    zones: list[GardenZone]
    devices: list[GardenDevice]
    alerts: list[AnalyticsEvent]
    activity: list[GardenActivityItem]
