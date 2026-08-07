"""
Unit tests for Phase 2 inference latency logging & admin endpoint.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from main import app
from services.metrics_store import METRICS_STORE


def test_metrics_store_starts_empty():
    """Verify the store starts with zero metrics — no fake seeded data."""
    fresh_store = type(METRICS_STORE)()  # New instance
    summary = fresh_store.summary(limit=10)
    assert summary["total_scans_logged"] == 0
    assert summary["average_ms"] == 0.0
    assert summary["p50_ms"] == 0.0
    assert summary["p95_ms"] == 0.0
    assert summary["by_model_source"] == {}


def test_metrics_store_recording_and_summary():
    """Record real entries and verify summary stats are computed correctly."""
    METRICS_STORE.record(inference_ms=120.5, model_source="yolov8", image_size=[640, 640])
    METRICS_STORE.record(inference_ms=350.2, model_source="plantnet", image_size=[640, 640])

    summary = METRICS_STORE.summary(limit=10)
    assert summary["total_scans_logged"] >= 2
    assert "average_ms" in summary
    assert "p50_ms" in summary
    assert "p95_ms" in summary
    assert "by_model_source" in summary
    assert summary["average_ms"] > 0


def test_admin_inference_summary_endpoint():
    client = TestClient(app)
    response = client.get("/admin/metrics/inference-summary")
    assert response.status_code == 200

    data = response.json()
    assert "total_scans_logged" in data
    assert "average_ms" in data
    assert "p50_ms" in data
    assert "p95_ms" in data
    assert "by_model_source" in data
