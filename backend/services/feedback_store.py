"""
Scan feedback store for Gemini/YOLO disagreement logging & human review (Phase 3).
"""

from __future__ import annotations

import datetime
import threading
import uuid
from typing import Any


class ScanFeedbackStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, dict[str, Any]] = {}

    def insert_feedback(
        self,
        *,
        image_ref: str,
        yolo_label: str,
        yolo_confidence: float,
        gemini_label: str,
        gemini_agrees: bool,
        reasoning: str = "",
    ) -> dict[str, Any]:
        item_id = str(uuid.uuid4())
        record = {
            "id": item_id,
            "image_ref": image_ref,
            "yolo_label": yolo_label,
            "yolo_confidence": round(float(yolo_confidence), 4),
            "gemini_label": gemini_label,
            "gemini_agrees": bool(gemini_agrees),
            "reasoning": reasoning,
            "reviewed": False,
            "confirmed_label": None,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        with self._lock:
            self._items[item_id] = record
        return record

    def list_pending(self) -> list[dict[str, Any]]:
        with self._lock:
            pending = [item for item in self._items.values() if not item["reviewed"]]
            return sorted(pending, key=lambda x: x["created_at"], reverse=True)

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted(list(self._items.values()), key=lambda x: x["created_at"], reverse=True)

    def confirm(self, item_id: str, confirmed_label: str) -> dict[str, Any] | None:
        with self._lock:
            if item_id not in self._items:
                return None
            item = self._items[item_id]
            item["reviewed"] = True
            item["confirmed_label"] = confirmed_label
            return dict(item)

    def get(self, item_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._items.get(item_id)


FEEDBACK_STORE = ScanFeedbackStore()
