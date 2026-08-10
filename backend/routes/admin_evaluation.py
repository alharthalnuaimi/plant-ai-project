from fastapi import APIRouter
import json
from pathlib import Path

from config.paths import REPO_ROOT

router = APIRouter(prefix="/admin/evaluation", tags=["admin"])

@router.get("/summary")
async def get_evaluation_summary():
    """
    Scans docs/evaluation/<species>/metrics.json and returns a combined summary.
    """
    eval_dir = REPO_ROOT / "docs" / "evaluation"
    species_list = ["money_plant", "cucumber", "rose"]
    result = {"species": {}}
    
    for species in species_list:
        metrics_file = eval_dir / species / "metrics.json"
        if metrics_file.exists():
            try:
                with open(metrics_file, "r") as f:
                    result["species"][species] = json.load(f)
            except Exception:
                result["species"][species] = "not yet evaluated — error reading metrics"
        else:
            result["species"][species] = "not yet evaluated — no dataset available"
            
    return result
