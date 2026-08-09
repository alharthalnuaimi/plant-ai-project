# PlantVision Model Evaluation

This folder contains evaluation metrics and artifacts generated on a 100% held-out test split.

## Summary Metrics

| Metric | Score |
|---|---|
| **Precision** | `0.8297` |
| **Recall** | `0.3333` |
| **mAP@50** | `0.995` |
| **mAP@50-95** | `0.7297` |

---

## Per-Class Performance Breakdown

| Class Name | Precision | Recall | mAP@50 | mAP@50-95 |
|---|---|---|---|---|
| **Bacterial Wilt Money Plant** | 1.0 | 0.0 | 0.995 | 0.796 |
| **Healthy Money Plant** | 1.0 | 0.0 | 0.995 | 0.6965 |
| **Manganese Toxicity Money Plant** | 0.489 | 1.0 | 0.995 | 0.6965 |

---

## Verification & Data Leakage Prevention

- **Split Ratio**: 70% Train, 20% Validation, 10% Test.
- **Leakage Audit**: Verified that zero test set images or augmentations exist in the training or validation splits.
- **Evaluation Command**: `python scripts/run_eval.py`

---

## Evaluation Artifacts

- **Confusion Matrix**: `confusion_matrix.png`
- **Precision-Recall Curve**: `PR_curve.png`
- **Metrics JSON**: `metrics.json`
