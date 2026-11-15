# DISABLED — kept for reference / future re-enablement only.
#
# Since the Gemini-only migration, production routes (/predict, /analyze,
# /report, /chat) never import or call this module. All diagnosis and
# reasoning goes through ``services.gemini``. Do not wire this back into a
# request path as a silent fallback: the stub predictors here produce
# made-up labels, and the canned narratives are not AI output.
# See docs/architecture/gemini-migration.md.

from .disease_model import DiseasePrediction, get_vision_predictor
from .llama_model import LlamaClient, get_llama_client
from .plant_id_model import (
    PlantIdPrediction,
    PlantIdPredictor,
    StubPlantIdPredictor,
    get_plant_id_predictor,
)

__all__ = [
    "DiseasePrediction",
    "get_vision_predictor",
    "LlamaClient",
    "get_llama_client",
    "PlantIdPrediction",
    "PlantIdPredictor",
    "StubPlantIdPredictor",
    "get_plant_id_predictor",
]
