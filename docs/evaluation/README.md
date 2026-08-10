# PlantVision — Model Evaluation Results

Each species has its own evaluation subfolder containing `metrics.json`, confusion matrices, PR curves, and a detailed README.

## Species

| Species | Status | Folder |
|---|---|---|
| **Money Plant** | ✅ Evaluated | [`money_plant/`](money_plant/) |
| **Cucumber** | ⚠️ Checkpoint metrics (no local test dataset) | [`cucumber/`](cucumber/) |
| **Rose** | ❌ Pending dataset | — |

## Re-running Evaluation

```bash
python scripts/run_eval.py --species money_plant
python scripts/run_eval.py --species cucumber
python scripts/run_eval.py --species rose
```

Results are written to `docs/evaluation/<species>/metrics.json` automatically.
