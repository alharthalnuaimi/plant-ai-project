"""Tests for ScanMetricsStore — record, summary, edge cases (Task 9)."""

from services.metrics_store import ScanMetricsStore


def test_empty_store_returns_zeros():
    store = ScanMetricsStore()
    summary = store.summary(limit=10)
    assert summary["total_scans_logged"] == 0
    assert summary["average_ms"] == 0.0
    assert summary["p50_ms"] == 0.0
    assert summary["p95_ms"] == 0.0
    assert summary["by_model_source"] == {}


def test_record_and_summary():
    store = ScanMetricsStore()
    store.record(inference_ms=100.0, model_source="yolov8", image_size=[640, 640])
    store.record(inference_ms=200.0, model_source="yolov8", image_size=[640, 640])
    store.record(inference_ms=300.0, model_source="plantnet", image_size=[640, 640])

    summary = store.summary(limit=10)
    assert summary["total_scans_logged"] == 3
    assert summary["average_ms"] == 200.0
    assert summary["p50_ms"] == 200.0
    assert "yolov8" in summary["by_model_source"]
    assert "plantnet" in summary["by_model_source"]
    assert summary["by_model_source"]["yolov8"]["count"] == 2
    assert summary["by_model_source"]["plantnet"]["count"] == 1


def test_summary_respects_limit():
    store = ScanMetricsStore()
    for i in range(20):
        store.record(inference_ms=float(i * 10), model_source="test")

    summary = store.summary(limit=5)
    assert summary["total_scans_logged"] == 5


def test_record_returns_entry_shape():
    store = ScanMetricsStore()
    entry = store.record(inference_ms=42.5, model_source="test_model")
    assert "timestamp" in entry
    assert entry["inference_ms"] == 42.5
    assert entry["model_source"] == "test_model"
    assert entry["image_size"] == [640, 640]  # default
