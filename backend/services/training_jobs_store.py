"""
Training jobs store for Phase 7 (Colab & Local GPU training orchestration).

Write-through to Postgres when PERSISTENCE_BACKEND=postgres (Task 4).
Falls back to in-memory when not.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import threading
import uuid
from typing import Any

log = logging.getLogger("plantvision.training_jobs_store")

def _use_postgres() -> bool:
    return os.getenv("PERSISTENCE_BACKEND", "memory").lower() == "postgres"


def _fire_and_forget(coro):
    """Schedule async DB write without blocking the sync caller."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        pass


class TrainingJobsStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def create_job(
        self,
        dataset_batch_ids: list[str],
        target: str = "local",
        metrics_before: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        record = {
            "id": job_id,
            "dataset_batch_ids": dataset_batch_ids,
            "target": target.lower(),
            "status": "queued",
            "metrics_before": metrics_before,
            "metrics_before_note": None if metrics_before else "No baseline metrics available — run evaluation first",
            "metrics_after": None,
            "weights_url": None,
            "error_message": None,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
        }
        with self._lock:
            self._jobs[job_id] = record

        # Write-through to Postgres
        if _use_postgres():
            try:
                from repositories.training_jobs_repo import insert_job as db_insert
                _fire_and_forget(db_insert(record=record))
            except Exception as exc:
                log.warning("DB write-through failed for job %s: %s", job_id, exc)

        return record

    def list_jobs(self, status: str | None = None, target: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            items = list(self._jobs.values())
            if status:
                items = [j for j in items if j["status"] == status.lower()]
            if target:
                items = [j for j in items if j["target"] == target.lower()]
            return sorted(items, key=lambda x: x["created_at"], reverse=True)

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_status(self, job_id: str, status: str, **kwargs: Any) -> dict[str, Any] | None:
        with self._lock:
            if job_id not in self._jobs:
                return None
            job = self._jobs[job_id]
            job["status"] = status
            if status == "running" and not job["started_at"]:
                job["started_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            if status in ("done", "failed"):
                job["completed_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for k, v in kwargs.items():
                job[k] = v
            updates = dict(job)

        # Write-through to Postgres
        if _use_postgres():
            try:
                from repositories.training_jobs_repo import update_job_status as db_update
                _fire_and_forget(db_update(job_id=job_id, updates={
                    "status": status,
                    "started_at": updates.get("started_at"),
                    "completed_at": updates.get("completed_at"),
                    **{k: v for k, v in kwargs.items()},
                }))
            except Exception as exc:
                log.warning("DB write-through failed for job update %s: %s", job_id, exc)

        return updates


TRAINING_JOBS_STORE = TrainingJobsStore()
