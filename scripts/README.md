# PlantVision Scripts

This directory contains standalone scripts for model evaluation, training, and dataset management.

## Training & Evaluation Requirements

To keep the main API backend lightweight, heavy machine learning dependencies (like PyTorch and Ultralytics) are NOT included in the core `backend/requirements.txt`.

Before running any scripts in this directory (such as `run_eval.py` or `retrain.py`), you must install the training requirements in your environment:

```bash
pip install -r requirements-training.txt
```

This architecture ensures that Railway deployments remain fast and small, while heavy GPU/training dependencies are restricted to local or Colab environments where training and evaluation actually happen.
