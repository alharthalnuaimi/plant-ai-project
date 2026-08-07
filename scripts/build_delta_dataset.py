"""
Script to build dataset/delta/ from confirmed human reviews in scan_feedback (Phase 5).

Only exports entries where the actual source image exists on disk.
Skips entries with missing images (logs a warning) instead of generating
fake placeholder images that would pollute the training data.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

log = logging.getLogger("plantvision.build_delta")


def build_delta_dataset() -> dict[str, int]:
    """Export confirmed feedback entries into YOLO annotation format.

    Returns summary dict with total_reviewed, exported_images, skipped counts.
    """
    base_dir = Path("d:/antigravity/M.P.AI")

    # Import with sys.path setup for standalone execution
    import sys
    sys.path.insert(0, str(base_dir / "backend"))
    from services.feedback_store import FEEDBACK_STORE

    delta_dir = base_dir / "dataset" / "delta"
    images_dir = delta_dir / "images"
    labels_dir = delta_dir / "labels"
    images_dir.mkdir(parents=True, exist_ok=True)
    labels_dir.mkdir(parents=True, exist_ok=True)

    class_mapping = {
        "Bacterial Wilt Money Plant": 0,
        "Healthy Money Plant": 1,
        "Manganese Toxicity Money Plant": 2,
        # Lowercase variants for fuzzy matching
        "bacterial wilt": 0,
        "healthy": 1,
        "manganese toxicity": 2,
    }

    all_feedback = FEEDBACK_STORE.list_all()
    reviewed_items = [f for f in all_feedback if f.get("reviewed") and f.get("confirmed_label")]

    exported_count = 0
    skipped_count = 0
    print(f"Found {len(reviewed_items)} confirmed feedback item(s) to convert into delta dataset...")

    for item in reviewed_items:
        item_id = item["id"]
        confirmed_label = item["confirmed_label"]

        # Resolve class ID — try exact match, then lowercase, then default to 1 (healthy)
        class_id = class_mapping.get(confirmed_label)
        if class_id is None:
            class_id = class_mapping.get(confirmed_label.lower(), 1)
            log.info("Label '%s' not in class mapping — defaulting to class %d", confirmed_label, class_id)

        file_stem = f"delta_{item_id[:8]}"
        img_dest = images_dir / f"{file_stem}.jpg"
        lbl_dest = labels_dir / f"{file_stem}.txt"

        # Locate the source image
        src_ref = item.get("image_ref", "")
        src_path = None
        if src_ref:
            # Try multiple resolution paths
            candidates = [
                base_dir / "backend" / src_ref,
                base_dir / src_ref,
                Path(src_ref),
            ]
            for candidate in candidates:
                if candidate.exists() and candidate.is_file():
                    src_path = candidate
                    break

        if src_path is not None:
            shutil.copy(src_path, img_dest)
        else:
            # SKIP — do not generate fake images for training data
            log.warning(
                "Source image not found for feedback %s (ref='%s') — skipping. "
                "Only real images are included in the delta dataset.",
                item_id[:8], src_ref,
            )
            skipped_count += 1
            continue

        # Write YOLO annotation label file: class x_center y_center width height
        lbl_dest.write_text(f"{class_id} 0.5 0.5 0.7 0.7\n")
        exported_count += 1

    summary = {
        "total_reviewed": len(reviewed_items),
        "exported_images": exported_count,
        "skipped_missing": skipped_count,
        "delta_dir": str(delta_dir),
    }
    print(f"[OK] Delta dataset built: {exported_count} images exported, {skipped_count} skipped (missing source).")
    return summary


if __name__ == "__main__":
    build_delta_dataset()
