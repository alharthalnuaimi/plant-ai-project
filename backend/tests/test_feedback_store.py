"""Tests for ScanFeedbackStore — insert, list, confirm, get (Task 9)."""

from services.feedback_store import ScanFeedbackStore


def test_insert_and_list_pending():
    store = ScanFeedbackStore()
    item = store.insert_feedback(
        image_ref="uploads/test.jpg",
        yolo_label="Bacterial Wilt",
        yolo_confidence=0.72,
        gemini_label="Healthy",
        gemini_agrees=False,
        reasoning="No visible symptoms.",
    )
    assert item["id"]
    assert item["reviewed"] is False
    assert item["yolo_label"] == "Bacterial Wilt"

    pending = store.list_pending()
    assert len(pending) >= 1
    assert any(p["id"] == item["id"] for p in pending)


def test_confirm_removes_from_pending():
    store = ScanFeedbackStore()
    item = store.insert_feedback(
        image_ref="uploads/test2.jpg",
        yolo_label="Powdery Mildew",
        yolo_confidence=0.65,
        gemini_label="Healthy",
        gemini_agrees=False,
    )
    confirmed = store.confirm(item["id"], confirmed_label="Healthy Money Plant")
    assert confirmed is not None
    assert confirmed["reviewed"] is True
    assert confirmed["confirmed_label"] == "Healthy Money Plant"

    pending = store.list_pending()
    assert not any(p["id"] == item["id"] for p in pending)


def test_list_all_includes_reviewed_and_pending():
    store = ScanFeedbackStore()
    item1 = store.insert_feedback(
        image_ref="a.jpg", yolo_label="A", yolo_confidence=0.5,
        gemini_label="B", gemini_agrees=False,
    )
    item2 = store.insert_feedback(
        image_ref="b.jpg", yolo_label="C", yolo_confidence=0.6,
        gemini_label="D", gemini_agrees=True,
    )
    store.confirm(item1["id"], "A Confirmed")

    all_items = store.list_all()
    assert len(all_items) == 2


def test_get_returns_none_for_missing():
    store = ScanFeedbackStore()
    assert store.get("nonexistent-id") is None


def test_confirm_returns_none_for_missing():
    store = ScanFeedbackStore()
    assert store.confirm("nonexistent-id", "label") is None
