"""
Unit tests for Phase 3 Gemini second opinion & feedback review endpoints.
"""

from __future__ import annotations

import io
from PIL import Image
from fastapi.testclient import TestClient
from main import app
from services.feedback_store import FEEDBACK_STORE
from services.gemini_second_opinion import evaluate_gemini_second_opinion


def test_feedback_store_and_gemini_eval():
    # Test manual insertion into feedback store
    entry = FEEDBACK_STORE.insert_feedback(
        image_ref="uploads/test_scan.jpg",
        yolo_label="Powdery Mildew",
        yolo_confidence=0.52,
        gemini_label="Leaf Spot",
        gemini_agrees=False,
        reasoning="Lesion shape resembles Leaf Spot.",
    )
    assert entry["id"] is not None
    assert entry["reviewed"] is False

    # List pending
    pending = FEEDBACK_STORE.list_pending()
    assert any(p["id"] == entry["id"] for p in pending)

    # Human confirmation
    confirmed = FEEDBACK_STORE.confirm(entry["id"], confirmed_label="Leaf Spot")
    assert confirmed["reviewed"] is True
    assert confirmed["confirmed_label"] == "Leaf Spot"

    # Pending list should no longer include confirmed entry
    pending_after = FEEDBACK_STORE.list_pending()
    assert not any(p["id"] == entry["id"] for p in pending_after)


def test_admin_feedback_endpoints():
    client = TestClient(app)

    # Create a pending item
    item = FEEDBACK_STORE.insert_feedback(
        image_ref="uploads/test_scan2.jpg",
        yolo_label="Bacterial Wilt",
        yolo_confidence=0.48,
        gemini_label="Healthy",
        gemini_agrees=False,
        reasoning="Visual symptoms look healthy.",
    )

    # Call GET /admin/feedback/pending
    res_get = client.get("/admin/feedback/pending")
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert isinstance(data_get, list)
    assert any(i["id"] == item["id"] for i in data_get)

    # Call POST /admin/feedback/{id}/confirm
    res_post = client.post(
        f"/admin/feedback/{item['id']}/confirm",
        json={"confirmed_label": "Healthy Money Plant"},
    )
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert data_post["reviewed"] is True
    assert data_post["confirmed_label"] == "Healthy Money Plant"


def test_predict_response_has_gemini_fields():
    client = TestClient(app)
    # Generate 640x640 sample JPEG
    img = Image.new("RGB", (640, 640), color=(50, 150, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    buf.seek(0)

    res = client.post(
        "/predict",
        files={"file": ("sample.jpg", buf, "image/jpeg")},
        data={"user_id": "test_user"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "gemini_verdict" in data
    assert "gemini_agrees" in data
    assert "gemini_reasoning" in data
