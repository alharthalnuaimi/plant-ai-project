# Local plant dataset (custom / agricultural)

This repo supports **your** field-collected data first. Public datasets are optional reference only.

## Two supported layouts

### 1) Image classification folders (quick starts, MobileNet / ViT later)

Use when every image belongs to **one** class (folder name = label):

```text
dataset/classification/
  train/<class_name>/*.jpg
  valid/<class_name>/*.jpg
  test/<class_name>/*.jpg
```

Default class folders (edit freely to match your taxonomy):

- `healthy`
- `diseased` (split further later, e.g. `diseased_powdery_mildew`, or keep coarse then refine)
- `dehydrated`
- `nutrient_deficient`

**Tip:** Prefer **specific disease folders** once labeling volume grows (e.g. `diseased_rust`, `diseased_blight`) instead of one giant `diseased` bucket.

### 2) YOLOv8 (Ultralytics) — detection or classification `.pt`

```text
dataset/yolov8/
  data.yaml
  images/train/
  images/val/
  images/test/          # optional
  labels/train/         # one .txt per image (same stem), or omit for YOLO-cls folder layout
  labels/val/
```

Point `data.yaml` `names` at **your** local class IDs. The API reads this file for `/dataset/info` and training scripts snapshot it into `artifacts/models/<version>/`.

## Organizing captures

- **One plant / one leaf per image** when possible; consistent distance and lighting reduce label noise.
- Store **raw** and **processed** separately if you apply crops: e.g. `raw/` (immutable) vs `dataset/...` (model-ready).
- Keep a **simple spreadsheet or CSV** alongside images: `image_id`, `class`, `site`, `date`, `species`, `notes` — invaluable for audits and retraining.

## Labeling workflow (practical)

1. Define a **closed label set** (version it, e.g. `labels_v2026_05.md`).
2. Use any tool that exports YOLO or folder names: Label Studio, CVAT, Roboflow, or manual folders for small pilots.
3. Hold out **geographic or temporal** validation when data allows (e.g. farm A train, farm B val) to measure real generalization.

## Preprocessing

- **Inference and training should share rules:** RGB, optional EXIF orientation fix, max resolution cap, and (for YOLO) the same `imgsz` you train with.
- Backend helper: `backend/services/preprocess.py` (`standardize_for_model`).
- Heavy augmentation (mosaic, etc.) belongs in **training** only, not in the API path.

## Training pipeline (see `training/`)

- Config and scripts live under `training/` so the FastAPI service stays lean.
- Each train run should write a **versioned** checkpoint under `artifacts/models/<version>/` and update `artifacts/registry.json`.

## Model versioning

- **Semantic version** per train: `v0.3.0` + optional git SHA in `metrics.json`.
- Never overwrite `best.pt` in place; create a new version folder and switch `active` in the registry (or set `YOLO_WEIGHTS_PATH` for one-off experiments).

## Updating the model later

1. Add images to `dataset/` (same schema).
2. Run `training/scripts/validate_layout.py`.
3. Train with `training/scripts/train_yolov8.py` (or your notebook).
4. Bump registry `active` to the new version; restart API (or hot-reload env in orchestrator).

## Git and large files

Binary weights and huge image dumps should not bloat git: use **Git LFS**, **cloud object storage**, or keep datasets local and document the path in `artifacts/registry.json` / team wiki.

## Backend environment overrides (optional)

| Variable | Purpose |
|----------|---------|
| `YOLO_DATA_YAML` | Path to your `data.yaml` if not `dataset/yolov8/data.yaml` |
| `CLASSIFICATION_DATASET_ROOT` | Root folder for folder-based classification layout |
| `YOLO_WEIGHTS_PATH` | Explicit `.pt` for inference (overrides registry) |
| `MODEL_REGISTRY_PATH` | Custom `registry.json` path |
| `STANDARDIZE_IMAGE_ON_PREDICT` | `1` / `true` to run EXIF + RGB + resize hygiene before vision |
| `MAX_IMAGE_SIDE` | Longest edge cap for uploads (e.g. `2048`) |
| `YOLO_CONF` / `YOLO_IMGSZ` | Inference confidence and size for Ultralytics |
