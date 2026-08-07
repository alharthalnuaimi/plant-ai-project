"""
Admin training route endpoints (Phase 7).
Exposes /admin/training/start, /admin/training/jobs, /admin/training/jobs/{id}, and completion route.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.training_jobs_store import TRAINING_JOBS_STORE

router = APIRouter(prefix="/admin/training", tags=["admin_training"])


class StartTrainingRequest(BaseModel):
    dataset_batch_ids: list[str] = Field(default_factory=list, description="IDs of 🟢 Ready dataset batches to include")
    target: str = Field(default="local", description="Execution target: 'colab' or 'local'")


class CompleteTrainingRequest(BaseModel):
    metrics_after: dict[str, Any] = Field(description="New model metrics achieved")
    weights_url: str | None = Field(default=None, description="URL or relative path to output weights")
    status: str = Field(default="done", description="'done' or 'failed'")
    error_message: str | None = Field(default=None, description="Error message if failed")


@router.post("/start")
async def start_training_job(payload: StartTrainingRequest) -> dict[str, Any]:
    """Queue a new remote or local training job."""
    target = payload.target.lower().strip()
    if target not in ("colab", "local"):
        raise HTTPException(status_code=400, detail="Target must be 'colab' or 'local'")

    job = TRAINING_JOBS_STORE.create_job(
        dataset_batch_ids=payload.dataset_batch_ids,
        target=target,
    )
    return job


@router.get("/jobs")
async def list_training_jobs(
    status: str | None = Query(default=None),
    target: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    """List training jobs by status or target."""
    return TRAINING_JOBS_STORE.list_jobs(status=status, target=target)


@router.get("/jobs/{job_id}")
async def get_training_job(job_id: str) -> dict[str, Any]:
    """Get training job details."""
    job = TRAINING_JOBS_STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Training job '{job_id}' not found")
    return job


@router.post("/jobs/{job_id}/complete")
async def complete_training_job(job_id: str, payload: CompleteTrainingRequest) -> dict[str, Any]:
    """Mark a training job complete or failed from agent."""
    job = TRAINING_JOBS_STORE.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Training job '{job_id}' not found")

    updated = TRAINING_JOBS_STORE.update_status(
        job_id,
        status=payload.status,
        metrics_after=payload.metrics_after,
        weights_url=payload.weights_url,
        error_message=payload.error_message,
    )
    return updated or {}
