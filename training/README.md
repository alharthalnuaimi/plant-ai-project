# Training and retraining (offline from API)

Keep **training** out of the request path: run these scripts on a workstation or CI GPU job, then promote weights via `artifacts/registry.json`.

## Setup

```bash
cd training
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements-train.txt
```

## Validate dataset layout

From repo root:

```bash
python training/scripts/validate_layout.py          # warn-only (OK on empty scaffold)
python training/scripts/validate_layout.py --strict # fail if folders are empty / mismatched
```

## Train YOLOv8 (example)

```bash
python training/scripts/train_yolov8.py --version v0.1.0 --epochs 50 --model yolov8n.pt
```

This writes:

- `artifacts/models/<version>/weights/best.pt` (Ultralytics default structure, then normalized)
- `artifacts/models/<version>/data.yaml` (snapshot)
- updates `artifacts/registry.json` if `--promote` is passed

## Model promotion

- **Dev:** set env `YOLO_WEIGHTS_PATH` to any `.pt` file.
- **Staging/prod:** set `active` in `artifacts/registry.json` to a trained version and optionally leave `YOLO_WEIGHTS_PATH` unset so the backend resolves weights automatically.

## Versioning discipline

- Bump **dataset version** (or export hash) when you change labels or splits.
- Bump **model semver** when you ship a new default checkpoint.
- Store `metrics.json` (mAP, confusion, val loss) next to each `best.pt` for auditability.
