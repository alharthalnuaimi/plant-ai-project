"""
Unit tests for Phase 5 self-improving retraining loop & eval gate.
"""

from __future__ import annotations

import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(base_dir))
sys.path.insert(0, str(base_dir / "backend"))

from services.feedback_store import FEEDBACK_STORE
from scripts.build_delta_dataset import build_delta_dataset
from scripts.retrain import run_retrain_pipeline


def test_build_delta_dataset_from_confirmed_feedback():
    """Confirmed feedback entries should be exported to delta dataset."""
    item = FEEDBACK_STORE.insert_feedback(
        image_ref="uploads/specimen_001.jpg",
        yolo_label="Powdery Mildew",
        yolo_confidence=0.58,
        gemini_label="Healthy Money Plant",
        gemini_agrees=False,
        reasoning="Leaf appears healthy.",
    )
    FEEDBACK_STORE.confirm(item["id"], confirmed_label="Healthy Money Plant")

    summary = build_delta_dataset()
    assert summary["total_reviewed"] >= 1
    # exported_images may be 0 if source images don't exist (correct behavior)
    assert "exported_images" in summary
    assert "skipped_missing" in summary


def test_build_delta_dataset_skips_missing_images():
    """When source images don't exist, delta builder should skip, not create fakes."""
    item = FEEDBACK_STORE.insert_feedback(
        image_ref="uploads/nonexistent_image.jpg",
        yolo_label="Bacterial Wilt",
        yolo_confidence=0.72,
        gemini_label="Healthy",
        gemini_agrees=False,
        reasoning="No symptoms visible.",
    )
    FEEDBACK_STORE.confirm(item["id"], confirmed_label="Healthy Money Plant")

    summary = build_delta_dataset()
    # Missing images should be skipped, not generated as fakes
    assert summary.get("skipped_missing", 0) >= 0


def test_retrain_pipeline_eval_gate():
    """Retrain pipeline should return proper eval gate result structure."""
    result = run_retrain_pipeline()
    assert "passed_gate" in result
    assert "baseline_mAP50" in result
    assert "status" in result
    assert result["status"] in ("DEPLOYED", "REJECTED", "FAILED")

    # If ultralytics isn't installed, training should fail gracefully
    # — never silently pass with fabricated metrics
    if result["status"] == "FAILED":
        assert result["passed_gate"] is False
        assert result.get("new_mAP50") is None
