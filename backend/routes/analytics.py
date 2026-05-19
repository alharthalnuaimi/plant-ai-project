from __future__ import annotations

from fastapi import APIRouter, Query

from schemas.analytics import (
    AnalyticsEvent,
    AnalyticsInsightsResponse,
    AnalyticsSummary,
    ScanHistoryItem,
    ZoneHealthSummary,
)
from schemas.garden import GardenDashboard
from services import analytics_store

router = APIRouter(tags=["analytics"])


@router.get("/analytics/summary", response_model=AnalyticsSummary)
async def analytics_summary() -> AnalyticsSummary:
    return analytics_store.get_summary()


@router.get("/analytics/history", response_model=list[ScanHistoryItem])
async def analytics_history(
    limit: int = Query(default=20, ge=1, le=100),
) -> list[ScanHistoryItem]:
    return analytics_store.get_history(limit=limit)


@router.get("/analytics/events", response_model=list[AnalyticsEvent])
async def analytics_events(
    limit: int = Query(default=30, ge=1, le=100),
) -> list[AnalyticsEvent]:
    return analytics_store.get_events(limit=limit)


@router.get("/analytics/zones", response_model=list[ZoneHealthSummary])
async def analytics_zones() -> list[ZoneHealthSummary]:
    return analytics_store.get_zones()


@router.get("/analytics/insights", response_model=AnalyticsInsightsResponse)
async def analytics_insights() -> AnalyticsInsightsResponse:
    items = analytics_store.get_insights()
    source = "live" if analytics_store.get_summary().total_scans > 0 else "demo"
    return AnalyticsInsightsResponse(items=items, source=source)


@router.get("/analytics/garden", response_model=GardenDashboard)
async def analytics_garden() -> GardenDashboard:
    return analytics_store.get_garden()
