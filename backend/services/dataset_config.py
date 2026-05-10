"""
Dataset introspection: local YOLO `data.yaml` + folder-based classification layout.
Used by API metadata routes and stub vision label pool — not for training (see `training/`).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from config.paths import REPO_ROOT

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _yaml_safe_load(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data if isinstance(data, dict) else {}


def default_data_yaml_path() -> Path:
    override = os.getenv("YOLO_DATA_YAML", "").strip()
    if override:
        return Path(override)
    return REPO_ROOT / "dataset" / "yolov8" / "data.yaml"


def default_classification_root() -> Path:
    override = os.getenv("CLASSIFICATION_DATASET_ROOT", "").strip()
    if override:
        return Path(override)
    return REPO_ROOT / "dataset" / "classification"


def get_yolo_class_names(data_yaml: Path | None = None) -> list[str]:
    """Ordered list of human-readable class names from `names` in data.yaml."""
    path = data_yaml or default_data_yaml_path()
    doc = _yaml_safe_load(path)
    names = doc.get("names")
    if isinstance(names, dict):
        items = sorted(((int(k), str(v)) for k, v in names.items()), key=lambda x: x[0])
        return [v for _, v in items]
    if isinstance(names, list):
        return [str(x) for x in names]
    return []


def validate_yolo_schema(data_yaml: Path | None = None) -> dict[str, Any]:
    path = data_yaml or default_data_yaml_path()
    doc = _yaml_safe_load(path)
    errors: list[str] = []
    warnings: list[str] = []
    if not path.is_file():
        errors.append(f"data.yaml not found: {path}")
        return {"ok": False, "errors": errors, "warnings": warnings}
    for key in ("train", "val"):
        if key not in doc:
            errors.append(f"Missing required key in data.yaml: {key}")
    names = get_yolo_class_names(path)
    if not names:
        errors.append("Missing or empty `names` in data.yaml")
    elif len(names) != len(set(n.strip().lower() for n in names)):
        errors.append("Duplicate class names found in data.yaml names")
    raw_names = doc.get("names")
    if isinstance(raw_names, dict):
        try:
            ids = sorted(int(k) for k in raw_names.keys())
            if ids != list(range(len(ids))):
                warnings.append("Class id mapping in `names` is not contiguous from 0..N-1")
        except Exception:
            errors.append("Class ids in `names` must be integers")
    if "test" not in doc:
        warnings.append("Optional `test` split is not defined in data.yaml")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def validate_classification_schema(root: Path | None = None) -> dict[str, Any]:
    base = root or default_classification_root()
    errors: list[str] = []
    warnings: list[str] = []
    if not base.is_dir():
        errors.append(f"classification root not found: {base}")
        return {"ok": False, "errors": errors, "warnings": warnings}
    expected_splits = ("train", "valid", "test")
    split_classes: dict[str, set[str]] = {}
    for split in expected_splits:
        sp = base / split
        if not sp.is_dir():
            warnings.append(f"missing split folder: {sp}")
            continue
        classes = {p.name for p in sp.iterdir() if p.is_dir()}
        split_classes[split] = classes
    if "train" in split_classes and "valid" in split_classes:
        if split_classes["train"] != split_classes["valid"]:
            warnings.append("train/valid class folders are not identical")
    if "test" in split_classes and "train" in split_classes:
        if not split_classes["test"].issubset(split_classes["train"]):
            warnings.append("test has classes not present in train")
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def classification_split_summary(root: Path | None = None) -> dict[str, Any]:
    base = root or default_classification_root()
    out: dict[str, Any] = {"root": str(base), "splits": {}}
    if not base.is_dir():
        return out
    for split in ("train", "valid", "test"):
        sp = base / split
        if not sp.is_dir():
            continue
        classes: dict[str, int] = {}
        for class_dir in sorted(p for p in sp.iterdir() if p.is_dir()):
            n = sum(1 for f in class_dir.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS)
            classes[class_dir.name] = n
        out["splits"][split] = classes
    return out


def yolo_folder_summary(data_yaml: Path | None = None) -> dict[str, Any]:
    path = data_yaml or default_data_yaml_path()
    doc = _yaml_safe_load(path)
    root = path.parent
    if doc.get("path"):
        root = (root / str(doc["path"])).resolve()

    def count_split(key: str) -> int:
        rel = doc.get(key)
        if not rel:
            return 0
        d = (root / str(rel)).resolve()
        if not d.is_dir():
            return 0
        return sum(1 for f in d.iterdir() if f.suffix.lower() in IMAGE_EXTENSIONS)

    return {
        "data_yaml": str(path),
        "resolved_root": str(root),
        "class_names": get_yolo_class_names(path),
        "counts": {
            "train_images": count_split("train"),
            "val_images": count_split("val"),
            "test_images": count_split("test"),
        },
    }


def dataset_info() -> dict[str, Any]:
    yolo_validation = validate_yolo_schema()
    cls_validation = validate_classification_schema()
    return {
        "repo_root": str(REPO_ROOT),
        "yolo": yolo_folder_summary(),
        "classification": classification_split_summary(),
        "validation": {
            "yolo": yolo_validation,
            "classification": cls_validation,
            "ok": yolo_validation["ok"] and cls_validation["ok"],
        },
    }
