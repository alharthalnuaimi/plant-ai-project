"""
Unit tests for Phase 7 training trigger & job queue orchestration.
"""

import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(base_dir))

from fastapi.testclient import TestClient
from main import app
from scripts.local_training_agent import process_local_jobs


def test_training_job_queue_and_agent_execution():
    client = TestClient(app)

    # Start job
    res_start = client.post(
        "/admin/training/start",
        json={"dataset_batch_ids": ["batch_001"], "target": "local"},
    )
    assert res_start.status_code == 200
    job_data = res_start.json()
    assert job_data["status"] == "queued"
    job_id = job_data["id"]

    # Poll jobs list
    res_list = client.get("/admin/training/jobs?status=queued&target=local")
    assert res_list.status_code == 200
    jobs_list = res_list.json()
    assert any(j["id"] == job_id for j in jobs_list)

    # Process job using agent
    processed = process_local_jobs()
    assert processed >= 1

    # Verify job status is done
    res_get = client.get(f"/admin/training/jobs/{job_id}")
    assert res_get.status_code == 200
    updated_job = res_get.json()
    assert updated_job["status"] == "done"
    assert updated_job["metrics_after"] is not None
