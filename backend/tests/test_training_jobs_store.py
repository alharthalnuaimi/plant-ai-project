"""Tests for TrainingJobsStore — create, list, update, edge cases (Task 9)."""

from services.training_jobs_store import TrainingJobsStore


def test_create_job_no_fabricated_metric():
    """Task 3 acceptance: no 0.941 fallback — metrics_before is None when not supplied."""
    store = TrainingJobsStore()
    job = store.create_job(dataset_batch_ids=["batch_001"])
    assert job["metrics_before"] is None
    assert job["metrics_before_note"] is not None
    assert "run evaluation" in job["metrics_before_note"].lower()


def test_create_job_with_real_metrics():
    store = TrainingJobsStore()
    real_metrics = {"mAP50": 0.82, "precision": 0.78}
    job = store.create_job(
        dataset_batch_ids=["batch_001"],
        metrics_before=real_metrics,
    )
    assert job["metrics_before"] == real_metrics
    assert job["metrics_before_note"] is None


def test_list_jobs_filter_by_status():
    store = TrainingJobsStore()
    store.create_job(dataset_batch_ids=["b1"])
    store.create_job(dataset_batch_ids=["b2"])

    all_jobs = store.list_jobs()
    assert len(all_jobs) == 2

    queued = store.list_jobs(status="queued")
    assert len(queued) == 2


def test_update_status_sets_timestamps():
    store = TrainingJobsStore()
    job = store.create_job(dataset_batch_ids=["b1"])
    job_id = job["id"]

    updated = store.update_status(job_id, "running")
    assert updated["status"] == "running"
    assert updated["started_at"] is not None

    completed = store.update_status(job_id, "done", metrics_after={"mAP50": 0.85})
    assert completed["status"] == "done"
    assert completed["completed_at"] is not None
    assert completed["metrics_after"]["mAP50"] == 0.85


def test_update_nonexistent_returns_none():
    store = TrainingJobsStore()
    assert store.update_status("fake-id", "done") is None


def test_get_job():
    store = TrainingJobsStore()
    job = store.create_job(dataset_batch_ids=["b1"], target="colab")
    retrieved = store.get_job(job["id"])
    assert retrieved is not None
    assert retrieved["target"] == "colab"


def test_get_nonexistent_returns_none():
    store = TrainingJobsStore()
    assert store.get_job("nonexistent") is None
