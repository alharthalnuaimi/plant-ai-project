"""
Unit tests for Phase 6 dataset uploads & readiness checks.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from fastapi.testclient import TestClient
from main import app
from services.readiness_check import evaluate_dataset_readiness


def test_readiness_check_service(tmp_path: Path):
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    
    # Create sample image files
    for i in range(12):
        (images_dir / f"img_{i}.jpg").write_bytes(b"sample_jpeg_bytes")

    report = evaluate_dataset_readiness(tmp_path)
    assert report["total_images"] == 12
    assert "status" in report
    assert "agreement_rate" in report


def test_admin_dataset_upload_endpoint():
    client = TestClient(app)

    # Create dummy in-memory zip
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as z:
        z.writestr("images/test1.jpg", b"fake_img")
        z.writestr("labels/test1.txt", "0 0.5 0.5 0.5 0.5\n")
    zip_buf.seek(0)

    res = client.post(
        "/admin/datasets/upload",
        files={"file": ("dataset_test.zip", zip_buf, "application/zip")},
    )
    assert res.status_code == 200
    data = res.json()
    assert "upload_id" in data
    assert "status" in data

    # Test listing endpoint
    res_list = client.get("/admin/datasets")
    assert res_list.status_code == 200
    batches = res_list.json()
    assert isinstance(batches, list)
    assert any(b["upload_id"] == data["upload_id"] for b in batches)
