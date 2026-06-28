from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class PlantHealthScore(BaseModel):
    plant_health: int = Field(ge=0, le=100, description="Overall plant health 0-100")
    disease_risk: Literal["Low", "Medium", "High", "Critical"] = "Low"
    environment_stress: Literal["Low", "Medium", "High"] = "Low"
    survival_chance: int = Field(ge=0, le=100, description="Estimated survival 0-100")
    recommendation: str = ""
    class_name: str = ""
    disease_type: str = "unknown"
    source: Literal["live", "demo", "baseline"] = "baseline"

    @field_validator("disease_risk", "environment_stress", mode="before")
    @classmethod
    def _normalize_risk(cls, v: Any) -> Any:
        """Accept lowercase/mixed-case values from the database or frontend
        (e.g. 'medium', 'high') and normalize them to title-case so Pydantic's
        Literal check passes without a 422 validation error."""
        if isinstance(v, str):
            return v.capitalize()
        return v


# ---------------------------------------------------------------------------
# Phase 3 — sensor health endpoint
# ---------------------------------------------------------------------------


class SensorDeviceHealth(BaseModel):
    """Per-device freshness + last-seen state for /health/sensor."""

    device_id: str
    zone_id: str | None = None
    user_id: str | None = None
    freshness: Literal["live", "stale", "offline", "none"]
    age_seconds: float | None = None
    last_seen_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp of the most recent reading (UTC).",
    )
    source: Literal["memory", "postgres", "none"] = "none"
    has_reading: bool = False


class SensorHealthResponse(BaseModel):
    """Top-level payload for ``GET /health/sensor``.

    Reports overall sensor pipeline status (validation, persistence, retries)
    plus per-device freshness so the frontend can light up zone markers.
    """

    status: Literal["healthy", "degraded", "offline"]
    persistence_backend: Literal["postgres", "memory"]
    deployment: Literal["cloud", "local", "memory"]
    postgres_reachable: bool
    devices: list[SensorDeviceHealth] = Field(default_factory=list)
    retry_stats: dict[str, dict[str, int]] = Field(
        default_factory=dict,
        description="Per-operation retry counters (attempts/retries/successes/failures).",
    )
    recent_retry_events: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Last 10 retry breadcrumbs for diagnostics.",
    )
    validation_failures_24h: int = 0
    last_error: str | None = None

