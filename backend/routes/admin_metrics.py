"""
Admin metrics route (Phase 2): exposes GET /admin/metrics/inference-summary.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Query

from services.metrics_store import METRICS_STORE

router = APIRouter(prefix="/admin/metrics", tags=["admin_metrics"])


@router.get("/inference-summary")
async def get_inference_summary(
    limit: int = Query(default=100, ge=1, le=1000),
) -> dict[str, Any]:
    """Compute average, p50, p95 inference latency across recent scans."""
    return METRICS_STORE.summary(limit=limit)
