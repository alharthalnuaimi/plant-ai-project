"""
Train YOLOv8 on local `dataset/yolov8/data.yaml`, version artifacts, optionally promote registry.

Example:
  python training/scripts/train_yolov8.py --version v0.1.0 --epochs 50 --promote

Requires: pip install -r training/requirements-train.txt
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from ultralytics import YOLO

REPO_ROOT = Path(__file__).resolve().parents[2]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _merge_registry(registry_path: Path, version: str, entry: dict, promote: bool) -> None:
    if registry_path.is_file():
        reg = json.loads(registry_path.read_text(encoding="utf-8"))
    else:
        reg = {"active": None, "versions": {}}
    versions = reg.get("versions") or {}
    versions[version] = entry
    reg["versions"] = versions
    if promote:
        reg["active"] = version
    registry_path.write_text(json.dumps(reg, indent=2), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--version", required=True, help="Semantic version folder, e.g. v0.1.0")
    p.add_argument(
        "--data",
        default=str(REPO_ROOT / "dataset" / "yolov8" / "data.yaml"),
        help="Ultralytics data.yaml",
    )
    p.add_argument("--model", default="yolov8n.pt", help="Base checkpoint from Ultralytics hub")
    p.add_argument("--epochs", type=int, default=50)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=16)
    p.add_argument(
        "--project",
        default=str(REPO_ROOT / "artifacts" / "train_runs"),
        help="Ultralytics project directory",
    )
    p.add_argument("--promote", action="store_true", help="Set registry active to this version")
    args = p.parse_args()

    data_yaml = Path(args.data).resolve()
    if not data_yaml.is_file():
        raise SystemExit(f"data yaml not found: {data_yaml}")

    out_root = REPO_ROOT / "artifacts" / "models" / args.version
    out_root.mkdir(parents=True, exist_ok=True)

    model = YOLO(args.model)
    train_kw = dict(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        project=args.project,
        name=args.version,
        exist_ok=True,
    )
    model.train(**train_kw)

    save_dir = Path(model.trainer.save_dir)
    best = save_dir / "weights" / "best.pt"
    if not best.is_file():
        raise SystemExit(f"Training finished but best.pt not found at {best}")

    dest_pt = out_root / "best.pt"
    shutil.copy2(best, dest_pt)

    data_snapshot = out_root / "data.yaml"
    shutil.copy2(data_yaml, data_snapshot)

    metrics_path = out_root / "metrics.json"
    metrics_path.write_text(
        json.dumps(
            {
                "version": args.version,
                "created_utc": _utc_now(),
                "data_yaml": str(data_yaml),
                "base_model": args.model,
                "epochs": args.epochs,
                "imgsz": args.imgsz,
                "ultralytics_save_dir": str(save_dir),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    weights_rel = dest_pt.relative_to(REPO_ROOT).as_posix()
    data_rel = data_snapshot.relative_to(REPO_ROOT).as_posix()
    entry = {
        "weights_relative": weights_rel,
        "data_yaml_relative": data_rel,
        "metrics_relative": metrics_path.relative_to(REPO_ROOT).as_posix(),
        "created_utc": _utc_now(),
        "train_args": vars(args),
    }

    registry_path = REPO_ROOT / "artifacts" / "registry.json"
    _merge_registry(registry_path, args.version, entry, promote=args.promote)
    print(f"Wrote {dest_pt}")
    print(f"Registry: {registry_path} (active={args.promote})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
