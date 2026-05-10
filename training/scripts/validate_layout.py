"""
Validate local dataset folders before training.

Run from repo root:
  python training/scripts/validate_layout.py
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Install PyYAML: pip install pyyaml", file=sys.stderr)
    raise

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _count_images(d: Path) -> int:
    if not d.is_dir():
        return 0
    return sum(1 for f in d.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXT)


def validate_classification(root: Path) -> list[str]:
    issues: list[str] = []
    if not root.is_dir():
        issues.append(f"Missing classification root: {root}")
        return issues
    for split in ("train", "valid", "test"):
        sp = root / split
        if not sp.is_dir():
            issues.append(f"Optional split missing (create if needed): {sp}")
            continue
        class_dirs = [p for p in sp.iterdir() if p.is_dir()]
        if not class_dirs:
            issues.append(f"No class subfolders under {sp}")
            continue
        for c in class_dirs:
            n = _count_images(c)
            if n == 0:
                issues.append(f"No images in {c}")
    return issues


def validate_yolov8(data_yaml: Path) -> list[str]:
    issues: list[str] = []
    if not data_yaml.is_file():
        issues.append(f"Missing data.yaml: {data_yaml}")
        return issues
    doc = yaml.safe_load(data_yaml.read_text(encoding="utf-8")) or {}
    base = data_yaml.parent
    path = doc.get("path", ".")
    root = (base / str(path)).resolve()

    def check_split(key: str, need_labels: bool) -> None:
        rel = doc.get(key)
        if not rel:
            return
        img_dir = (root / str(rel)).resolve()
        if not img_dir.is_dir():
            issues.append(f"{key} image dir missing: {img_dir}")
            return
        images = [f for f in img_dir.iterdir() if f.suffix.lower() in IMAGE_EXT]
        if not images:
            issues.append(f"No images found for {key}: {img_dir}")
            return
        if not need_labels:
            return
        lab_key = "labels/" + str(Path(str(rel)).name)
        labels_dir = (root / lab_key).resolve()
        if not labels_dir.is_dir():
            issues.append(f"Expected labels next to images for detection: {labels_dir}")
            return
        missing = 0
        for img in images:
            lf = labels_dir / (img.stem + ".txt")
            if not lf.is_file():
                missing += 1
        if missing:
            issues.append(
                f"{key}: {missing}/{len(images)} images missing label file in {labels_dir}"
            )

    # If labels dirs exist under root, enforce detection pairing for train/val.
    labels_train = root / "labels" / "train"
    need_labels = labels_train.is_dir()
    check_split("train", need_labels=need_labels)
    check_split("val", need_labels=need_labels)
    check_split("test", need_labels=False)

    names = doc.get("names")
    if not names:
        issues.append("data.yaml: `names` should list your custom classes")

    return issues


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail if any checks fail (use before training). Default: warn-only for empty scaffold.",
    )
    args = parser.parse_args()

    cls_root = REPO_ROOT / "dataset" / "classification"
    yolo_yaml = REPO_ROOT / "dataset" / "yolov8" / "data.yaml"

    warnings: list[str] = []
    errors: list[str] = []

    for m in validate_classification(cls_root):
        (errors if "Missing classification root" in m else warnings).append("[classification] " + m)

    yolo_msgs = validate_yolov8(yolo_yaml)
    for m in yolo_msgs:
        bucket = errors if m.startswith("Missing data.yaml") or "data.yaml:" in m else warnings
        bucket.append("[yolov8] " + m)

    if warnings:
        print("Dataset layout warnings:\n- " + "\n- ".join(warnings))
    if errors:
        print("Dataset layout errors:\n- " + "\n- ".join(errors))

    if errors:
        return 1
    if args.strict and warnings:
        return 1
    if not warnings and not errors:
        print("Dataset layout OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
