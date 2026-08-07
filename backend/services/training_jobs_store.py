"""
Training jobs store for Phase 7 (Colab & Local GPU training orchestration).
"""

from __future__ import annotations

import datetime
import threading
import uuid
from typing import Any


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
            "metrics_before": metrics_before or {"mAP50": 0.941},
            "metrics_after": None,
            "weights_url": None,
            "error_message": None,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
        }
        with self._lock:
            self._jobs[job_id] = record
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
            return dict(job)


TRAINING_JOBS_STORE = TrainingJobsStore()
