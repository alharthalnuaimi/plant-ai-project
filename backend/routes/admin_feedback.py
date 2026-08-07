"""
Admin feedback review endpoints (Phase 3).
Exposes GET /admin/feedback/pending and POST /admin/feedback/{id}/confirm.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.feedback_store import FEEDBACK_STORE

router = APIRouter(prefix="/admin/feedback", tags=["admin_feedback"])


class ConfirmFeedbackRequest(BaseModel):
    confirmed_label: str = Field(description="Human-confirmed correct disease/health label")


@router.get("/pending")
async def get_pending_feedback() -> list[dict[str, Any]]:
    """List unreviewed scan feedback cases where Gemini & YOLO disagreed or confidence was low."""
    return FEEDBACK_STORE.list_pending()


@router.post("/{item_id}/confirm")
async def confirm_feedback(item_id: str, payload: ConfirmFeedbackRequest) -> dict[str, Any]:
    """Human confirm a label for a pending disagreement case."""
    updated = FEEDBACK_STORE.confirm(item_id, confirmed_label=payload.confirmed_label)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Feedback item '{item_id}' not found")
    return updated
