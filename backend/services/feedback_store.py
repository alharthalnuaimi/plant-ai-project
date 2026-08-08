"""
Scan feedback store for Gemini/YOLO disagreement logging & human review (Phase 3).

Write-through to Postgres when PERSISTENCE_BACKEND=postgres (Task 4).
Falls back to in-memory when not — same graceful-degradation pattern as the
rest of the app. Public method signatures are unchanged.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import threading
import uuid
from typing import Any

log = logging.getLogger("plantvision.feedback_store")

def _use_postgres() -> bool:
    return os.getenv("PERSISTENCE_BACKEND", "memory").lower() == "postgres"


def _fire_and_forget(coro):
    """Schedule async DB write without blocking the sync caller."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        pass  # No running loop — skip DB write silently


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

        # Write-through to Postgres
        if _use_postgres():
            try:
                from repositories.feedback_repo import insert_feedback as db_insert
                _fire_and_forget(db_insert(record=record))
            except Exception as exc:
                log.warning("DB write-through failed for feedback %s: %s", item_id, exc)

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

        # Write-through to Postgres
        if _use_postgres():
            try:
                from repositories.feedback_repo import confirm_feedback as db_confirm
                _fire_and_forget(db_confirm(feedback_id=item_id, confirmed_label=confirmed_label))
            except Exception as exc:
                log.warning("DB write-through failed for confirm %s: %s", item_id, exc)

        return dict(item)

    def get(self, item_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._items.get(item_id)


FEEDBACK_STORE = ScanFeedbackStore()
