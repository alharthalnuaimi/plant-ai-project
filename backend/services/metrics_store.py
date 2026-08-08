"""
Scan metrics & inference time logging store (Phase 2).
Records timing, model source, and image sizes for real requests only.
No synthetic/fake data — summary returns zeros when no scans have been logged.

Write-through to Postgres when PERSISTENCE_BACKEND=postgres (Task 4).
Falls back to in-memory when not.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import math
import os
import statistics
import threading
from typing import Any

log = logging.getLogger("plantvision.metrics_store")

def _use_postgres() -> bool:
    return os.getenv("PERSISTENCE_BACKEND", "memory").lower() == "postgres"


def _fire_and_forget(coro):
    """Schedule async DB write without blocking the sync caller."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        pass


class ScanMetricsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._metrics: list[dict[str, Any]] = []

    def record(
        self,
        inference_ms: float,
        model_source: str = "yolov8",
        image_size: list[int] | tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        """Record a real inference timing entry from an actual /predict call."""
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "inference_ms": round(float(inference_ms), 2),
            "model_source": str(model_source),
            "image_size": list(image_size) if image_size else [640, 640],
        }
        with self._lock:
            self._metrics.append(entry)
            # Retain last 1000 items
            if len(self._metrics) > 1000:
                self._metrics = self._metrics[-1000:]

        # Write-through to Postgres
        if _use_postgres():
            try:
                from repositories.metrics_repo import insert_metric as db_insert
                _fire_and_forget(db_insert(
                    inference_ms=entry["inference_ms"],
                    model_source=entry["model_source"],
                    image_size=entry["image_size"],
                ))
            except Exception as exc:
                log.warning("DB write-through failed for metric: %s", exc)

        return entry

    def summary(self, limit: int = 100) -> dict[str, Any]:
        """Compute average, p50, p95 inference latency across recent scans.

        Returns zeros when no real scans have been logged — the plan
        explicitly requires real data, not synthetic/fake timing.
        """
        with self._lock:
            recent = self._metrics[-limit:] if limit > 0 else list(self._metrics)

        if not recent:
            return {
                "total_scans_logged": 0,
                "sample_size": 0,
                "average_ms": 0.0,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "by_model_source": {},
                "note": "No real inference data yet. Metrics populate after /predict requests.",
            }

        times = sorted([m["inference_ms"] for m in recent])
        n = len(times)
        avg = round(sum(times) / n, 2)
        p50 = round(statistics.median(times), 2)

        # Calculate p95 index safely
        p95_idx = min(n - 1, math.ceil(0.95 * n) - 1)
        p95 = round(times[p95_idx], 2)

        by_source: dict[str, list[float]] = {}
        for m in recent:
            src = m.get("model_source", "unknown")
            by_source.setdefault(src, []).append(m["inference_ms"])

        source_stats = {}
        for src, src_times in by_source.items():
            source_stats[src] = {
                "count": len(src_times),
                "avg_ms": round(sum(src_times) / len(src_times), 2),
                "p50_ms": round(statistics.median(src_times), 2),
            }

        return {
            "total_scans_logged": n,
            "sample_size": n,
            "average_ms": avg,
            "p50_ms": p50,
            "p95_ms": p95,
            "by_model_source": source_stats,
        }


# Module-level singleton — starts empty (no fake seeded data).
METRICS_STORE = ScanMetricsStore()
