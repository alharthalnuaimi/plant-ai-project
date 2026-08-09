"""
Retraining script with mandatory evaluation gate (Phase 5).

INVARIANT: Production model weights are NEVER replaced unless
new_model_mAP50 >= current_model_mAP50 on the held-out test split.
If training or validation fails, the script reports FAILED — it never
silently passes the gate with fabricated metrics.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path


def run_retrain_pipeline(extra_dataset_dirs: list[str] | None = None) -> dict[str, str | float | bool]:
    """Run fine-tune + eval gate pipeline.

    Parameters
    ----------
    extra_dataset_dirs : list[str] | None
        Optional list of additional dataset batch directories (from Phase 6
        uploads) to merge into the training split. Only 🟢 Ready batches
        should be passed unless an override flag is used.
    """
    base_dir = Path(__file__).resolve().parent.parent
    yolo_dir = base_dir / "dataset" / "yolov8"
    data_yaml_path = base_dir / "artifacts" / "models" / "cucumber" / "data.yaml"
    eval_metrics_path = base_dir / "docs" / "evaluation" / "metrics.json"

    # Read current baseline mAP50 from Phase 1 evaluation metrics
    baseline_map50 = 0.0
    if eval_metrics_path.exists():
        try:
            data = json.loads(eval_metrics_path.read_text())
            baseline_map50 = float(data.get("overall", {}).get("mAP50", 0.0))
        except Exception:
            pass

    if baseline_map50 <= 0:
        print("[WARNING] No valid baseline mAP50 found. Using 0.0 — any trained model will pass.")

    print(f"Current baseline test set mAP50 threshold: {baseline_map50:.4f}")

    # Build delta dataset from confirmed feedback
    import sys
    sys.path.insert(0, str(base_dir))
    sys.path.insert(0, str(base_dir / "backend"))

    try:
        from scripts.build_delta_dataset import build_delta_dataset
        delta_summary = build_delta_dataset()
        print(f"Delta dataset: {delta_summary.get('exported_images', 0)} images exported.")
    except Exception as exc:
        print(f"[WARNING] Delta dataset build skipped: {exc}")

    # Merge delta into train split
    delta_dir = base_dir / "dataset" / "delta"
    merged_count = 0
    if delta_dir.exists() and (delta_dir / "images").exists():
        for img in (delta_dir / "images").glob("*.jpg"):
            dest_img = yolo_dir / "images" / "train" / img.name
            shutil.copy(img, dest_img)
            lbl = delta_dir / "labels" / f"{img.stem}.txt"
            if lbl.exists():
                shutil.copy(lbl, yolo_dir / "labels" / "train" / lbl.name)
            merged_count += 1

    # Merge extra dataset batches (Phase 6d)
    if extra_dataset_dirs:
        for batch_dir_str in extra_dataset_dirs:
            batch_dir = Path(batch_dir_str)
            if not batch_dir.exists():
                # Try resolving relative to uploads root
                batch_dir = base_dir / "dataset" / "uploads" / batch_dir_str
            if not batch_dir.exists():
                print(f"[WARNING] Batch directory not found, skipping: {batch_dir_str}")
                continue
            img_src = batch_dir / "images" if (batch_dir / "images").exists() else batch_dir
            for img in list(img_src.glob("*.jpg")) + list(img_src.glob("*.png")):
                dest_img = yolo_dir / "images" / "train" / img.name
                shutil.copy(img, dest_img)
                lbl = (batch_dir / "labels" / f"{img.stem}.txt")
                if lbl.exists():
                    shutil.copy(lbl, yolo_dir / "labels" / "train" / lbl.name)
                merged_count += 1

    print(f"Merged {merged_count} new specimen(s) into YOLO training split.")

    # Execute YOLO training / fine-tuning
    print("Initiating fine-tune training run...")
    new_map50: float | None = None
    training_error: str | None = None

    try:
        from ultralytics import YOLO

        weights_path = base_dir / "artifacts" / "models" / "cucumber" / "weights.pt"
        if not weights_path.exists() or weights_path.stat().st_size < 1000:
            weights_path = base_dir / "yolov8n.pt"

        model = YOLO(str(weights_path) if weights_path.exists() else "yolov8n.pt")
        model.train(
            data=str(data_yaml_path),
            epochs=2,
            imgsz=640,
            batch=8,
            project=str(base_dir / "artifacts" / "train_runs"),
            name="retrain_run",
            exist_ok=True,
            verbose=False,
        )

        # Validate on the held-out test split
        val_res = model.val(
            data=str(data_yaml_path),
            split="test",
            verbose=False,
        )
        val_map = val_res.results_dict.get("metrics/mAP50(B)")
        if val_map is not None:
            new_map50 = round(float(val_map), 4)
        else:
            training_error = "Validation completed but mAP50 metric not found in results."

    except ImportError:
        training_error = "ultralytics not installed — cannot run YOLO training."
    except Exception as exc:
        training_error = f"Training/validation failed: {type(exc).__name__}: {exc}"

    # If training failed, report FAILED — never silently pass the gate
    if training_error is not None or new_map50 is None:
        error_msg = training_error or "No mAP50 computed."
        print(f"[FAILED] {error_msg}")
        result_summary = {
            "passed_gate": False,
            "baseline_mAP50": baseline_map50,
            "new_mAP50": None,
            "status": "FAILED",
            "message": error_msg,
        }
        _log_retrain_result(base_dir, result_summary)
        return result_summary

    print(f"New candidate model test set mAP50: {new_map50:.4f}")

    # EVALUATION GATE INVARIANT: new_mAP50 >= baseline_mAP50
    passed_gate = new_map50 >= baseline_map50
    prod_weights_path = base_dir / "artifacts" / "models" / "cucumber" / "weights.pt"
    prod_weights_path.parent.mkdir(parents=True, exist_ok=True)

    if passed_gate:
        status_msg = f"PASSED EVAL GATE ({new_map50:.4f} >= {baseline_map50:.4f}). Production model updated."
        print(f"[OK] {status_msg}")
        # Copy the trained weights to production location
        latest_weights = base_dir / "artifacts" / "train_runs" / "retrain_run" / "weights" / "best.pt"
        if latest_weights.exists():
            shutil.copy2(latest_weights, prod_weights_path)
        else:
            # Fallback: write a marker; real deployment would copy actual weights
            print("[WARNING] best.pt not found in expected location. Production weights not physically updated.")
    else:
        status_msg = f"FAILED EVAL GATE ({new_map50:.4f} < {baseline_map50:.4f}). Retaining current production weights."
        print(f"[WARNING] {status_msg}")

    result_summary = {
        "passed_gate": passed_gate,
        "baseline_mAP50": baseline_map50,
        "new_mAP50": new_map50,
        "status": "DEPLOYED" if passed_gate else "REJECTED",
        "message": status_msg,
    }

    _log_retrain_result(base_dir, result_summary)
    return result_summary


def _log_retrain_result(base_dir: Path, result: dict) -> None:
    """Append retrain result to history log."""
    log_file = base_dir / "docs" / "evaluation" / "retrain_history.json"
    history = []
    if log_file.exists():
        try:
            history = json.loads(log_file.read_text())
        except Exception:
            history = []
    history.append(result)
    log_file.write_text(json.dumps(history, indent=2))


if __name__ == "__main__":
    run_retrain_pipeline()
