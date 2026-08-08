"""Tests for readiness_check — thin classes, imbalance, duplicates (Task 9)."""

import os
import shutil
import tempfile
from pathlib import Path

from services.readiness_check import evaluate_dataset_readiness


def _make_batch(base_dir: Path, images: dict[str, bytes], labels: dict[str, str] | None = None):
    """Create a synthetic batch directory for testing."""
    img_dir = base_dir / "images"
    lbl_dir = base_dir / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    for name, content in images.items():
        (img_dir / name).write_bytes(content)
    if labels:
        for name, content in labels.items():
            (lbl_dir / name).write_text(content)


class TestReadinessCheck:
    def test_empty_batch_not_usable(self, tmp_path):
        batch = tmp_path / "empty_batch"
        batch.mkdir()
        result = evaluate_dataset_readiness(batch)
        assert "Not usable" in result["status"]
        assert result["total_images"] == 0

    def test_thin_class_flagged(self, tmp_path):
        batch = tmp_path / "thin_batch"
        # Create 3 images with class 0, 1 with class 1 — below min_images_per_class=10
        images = {f"img_{i}.jpg": b"\xff" * (100 + i) for i in range(4)}
        labels = {
            "img_0.txt": "0 0.5 0.5 0.7 0.7",
            "img_1.txt": "0 0.5 0.5 0.7 0.7",
            "img_2.txt": "0 0.5 0.5 0.7 0.7",
            "img_3.txt": "1 0.5 0.5 0.7 0.7",
        }
        _make_batch(batch, images, labels)
        result = evaluate_dataset_readiness(batch, min_images_per_class=5)
        assert "review" in result["status"].lower() or "not usable" in result["status"].lower()
        assert any("fewer" in issue.lower() for issue in result["issues"])

    def test_heavy_imbalance_flagged(self, tmp_path):
        batch = tmp_path / "imbalanced"
        # 20 class-0 images, 2 class-1 images — 10x imbalance
        images = {f"img_{i}.jpg": bytes([i % 256]) * (100 + i) for i in range(22)}
        labels = {}
        for i in range(20):
            labels[f"img_{i}.txt"] = "0 0.5 0.5 0.7 0.7"
        for i in range(20, 22):
            labels[f"img_{i}.txt"] = "1 0.5 0.5 0.7 0.7"
        _make_batch(batch, images, labels)

        result = evaluate_dataset_readiness(batch, min_images_per_class=2)
        assert len(result["class_balance_issues"]) > 0
        assert "imbalance" in result["class_balance_issues"][0].lower()

    def test_duplicates_detected(self, tmp_path):
        batch = tmp_path / "dupes"
        # Two images with identical content = duplicates
        same_content = b"\xff\xd8\xff" * 100
        images = {
            "img_a.jpg": same_content,
            "img_b.jpg": same_content,
            "img_c.jpg": b"\x00" * 300,  # different
        }
        labels = {
            "img_a.txt": "0 0.5 0.5 0.7 0.7",
            "img_b.txt": "0 0.5 0.5 0.7 0.7",
            "img_c.txt": "1 0.5 0.5 0.7 0.7",
        }
        _make_batch(batch, images, labels)
        result = evaluate_dataset_readiness(batch, min_images_per_class=1)
        assert result["duplicate_count"] >= 1

    def test_ready_batch(self, tmp_path):
        batch = tmp_path / "ready"
        # 15 images each for 2 classes, no duplicates, balanced
        images = {}
        labels = {}
        for i in range(30):
            content = bytes([i]) * (200 + i)  # unique content
            images[f"img_{i}.jpg"] = content
            cls = "0" if i < 15 else "1"
            labels[f"img_{i}.txt"] = f"{cls} 0.5 0.5 0.7 0.7"
        _make_batch(batch, images, labels)
        result = evaluate_dataset_readiness(batch, min_images_per_class=10)
        assert result["ready_to_train"] is True
        assert "Ready" in result["status"]
