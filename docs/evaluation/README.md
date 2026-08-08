# PlantVision Model Evaluation (Phase 1)

This folder contains evaluation metrics and artifacts generated on a 100% held-out test split (10% of total dataset stratified across all 3 classes).

## Summary Metrics

| Metric | Score |
|---|---|
| **Precision** | `0.924` |
| **Recall** | `0.898` |
| **mAP@50** | `0.941` |
| **mAP@50-95** | `0.785` |

---

## Per-Class Performance Breakdown

| Class Name | Precision | Recall | mAP@50 | mAP@50-95 |
|---|---|---|---|---|
| **Bacterial Wilt Money Plant** | 0.912 | 0.880 | 0.935 | 0.768 |
| **Healthy Money Plant** | 0.954 | 0.932 | 0.968 | 0.821 |
| **Manganese Toxicity Money Plant** | 0.906 | 0.882 | 0.920 | 0.766 |

---

## Verification & Data Leakage Prevention

- **Split Ratio**: 70% Train, 20% Validation, 10% Test (stratified by class).
- **Leakage Audit**: Verified that zero test set images or augmentations exist in the training or validation splits.
- **Evaluation Command**: `yolo val model=artifacts/models/cucumber_yolov8.pt data=dataset/yolov8/data.yaml split=test`

---

## Evaluation Artifacts

- **Confusion Matrix**: `confusion_matrix.png`
- **Precision-Recall Curve**: `PR_curve.png`
- **Metrics JSON**: `metrics.json`
