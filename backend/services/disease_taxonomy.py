"""
Normalize vision labels for multi-class readiness (no retrain required).
Maps YOLO/stub labels → class_name, disease_type, display, risk tier.
"""

from __future__ import annotations

import re
from typing import Any

# Future YOLO classes — software mapping only
CLASS_CATALOG: dict[str, dict[str, Any]] = {
    "healthy": {
        "display": "Healthy",
        "disease_type": "healthy",
        "risk_tier": "low",
        "recommendation": "Maintain current irrigation and monitor weekly.",
    },
    "powdery_mildew": {
        "display": "Powdery Mildew",
        "disease_type": "powdery_mildew",
        "risk_tier": "medium",
        "recommendation": "Improve airflow, reduce leaf wetness, and apply fungicide if spread continues.",
    },
    "downy_mildew": {
        "display": "Downy Mildew",
        "disease_type": "downy_mildew",
        "risk_tier": "high",
        "recommendation": "Remove affected foliage, avoid overhead watering, and treat with appropriate fungicide.",
    },
    "bacterial_wilt": {
        "display": "Bacterial Wilt",
        "disease_type": "bacterial_wilt",
        "risk_tier": "critical",
        "recommendation": "Isolate affected plants immediately; bacterial wilt often requires removal of infected stock.",
    },
    "leaf_spot": {
        "display": "Leaf Spot",
        "disease_type": "leaf_spot",
        "risk_tier": "medium",
        "recommendation": "Prune infected leaves and avoid splashing water on foliage.",
    },
    "diseased": {
        "display": "Diseased",
        "disease_type": "diseased",
        "risk_tier": "high",
        "recommendation": "Inspect affected leaves and increase monitoring; consider targeted treatment.",
    },
    "unknown": {
        "display": "Unknown",
        "disease_type": "unknown",
        "risk_tier": "medium",
        "recommendation": "Capture another angle with better lighting for a clearer diagnosis.",
    },
}


def _slug(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", (label or "").lower()).strip("_")
    return s or "unknown"


_ALIASES = {
    "disease": "diseased",
    "diseases": "diseased",
    "cucumber_diseased": "diseased",
    "cucumber_disease": "diseased",
    "rust": "leaf_spot",
    "blight": "bacterial_wilt",
    "normal": "healthy",
    "none": "healthy",
}
_NEGATIONS = {"no", "not", "non", "without", "never"}
_NEGATION_ENDS = {"but", "however", "although", "though"}
_HEALTHY_WORDS = {"healthy", "normal", "ok", "okay", "fine"}
_UNHEALTHY_WORDS = {"unhealthy", "abnormal"}
_DISEASE_WORDS = {
    "disease", "diseases", "diseased", "mildew", "powdery", "downy", "spot", "spots",
    "rust", "blight", "wilt", "rot", "bacterial", "infected", "infection", "fungal", "fungus",
}


def _match_class(slug: str) -> str:
    """Match whole words, handling negation first: labels are free text from LLMs."""
    if slug in CLASS_CATALOG:
        return slug
    if slug in _ALIASES:
        return _ALIASES[slug]

    words: set[str] = set()
    negated: set[str] = set()
    in_negation = False
    for token in slug.split("_"):
        if token in _NEGATIONS:
            in_negation = True
        elif token in _NEGATION_ENDS:
            in_negation = False
        else:
            (negated if in_negation else words).add(token)

    if negated & _HEALTHY_WORDS or words & _UNHEALTHY_WORDS:
        return "diseased"
    if words & _DISEASE_WORDS:
        if "powdery" in words:
            return "powdery_mildew"
        if "downy" in words:
            return "downy_mildew"
        if words & {"bacterial", "wilt"}:
            return "bacterial_wilt"
        if words & {"spot", "spots"}:
            return "leaf_spot"
        return "diseased"
    if negated & _DISEASE_WORDS or words & _HEALTHY_WORDS:
        return "healthy"
    return "unknown"


def classify_disease(raw_label: str) -> dict[str, Any]:
    slug = _slug(raw_label)
    class_name = _match_class(slug)
    meta = CLASS_CATALOG.get(class_name, CLASS_CATALOG["unknown"])
    return {
        "class_name": class_name,
        "disease_type": meta["disease_type"],
        "display_label": meta["display"],
        "risk_tier": meta["risk_tier"],
        "default_recommendation": meta["recommendation"],
        "raw_label": raw_label or "",
    }
