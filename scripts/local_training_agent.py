"""
Local GPU / machine training agent (Phase 7c).

Polls for queued local training jobs and executes retraining pipeline.
Run with: python scripts/local_training_agent.py

The agent picks up queued jobs targeting 'local', runs the retrain
pipeline, and reports results back to the training jobs store.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(base_dir))
sys.path.insert(0, str(base_dir / "backend"))

from services.training_jobs_store import TRAINING_JOBS_STORE
from scripts.retrain import run_retrain_pipeline


def process_local_jobs() -> int:
    """Process all queued local training jobs.

    Returns number of jobs processed.
    """
    queued_jobs = TRAINING_JOBS_STORE.list_jobs(status="queued", target="local")
    if not queued_jobs:
        print("[Agent] No queued local jobs found.")
        return 0

    processed = 0
    for job in queued_jobs:
        job_id = job["id"]
        print(f"[Agent] Processing queued training job {job_id}...")
        TRAINING_JOBS_STORE.update_status(job_id, "running")

        try:
            res = run_retrain_pipeline(job.get("dataset_batch_ids"))

            # Report results — distinguish gate pass from gate fail
            passed = res.get("passed_gate", False)
            new_map = res.get("new_mAP50")
            status = res.get("status", "FAILED")

            TRAINING_JOBS_STORE.update_status(
                job_id,
                status="done",
                metrics_after={
                    "mAP50": new_map,
                    "passed_gate": passed,
                    "eval_status": status,
                    "message": res.get("message", ""),
                },
                weights_url="artifacts/models/cucumber_yolov8.pt" if passed else None,
            )
            print(f"[Agent] Job {job_id} completed: {status} (mAP50={new_map})")
            processed += 1

        except Exception as exc:
            print(f"[Agent] Job {job_id} failed with error: {exc}")
            TRAINING_JOBS_STORE.update_status(
                job_id,
                status="failed",
                error_message=str(exc),
            )

    return processed


if __name__ == "__main__":
    print("Local Training Agent initialized. Checking for queued jobs...")
    count = process_local_jobs()
    print(f"Finished processing {count} job(s).")
