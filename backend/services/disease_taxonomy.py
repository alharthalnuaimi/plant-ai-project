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


def _match_class(slug: str) -> str:
    if slug in CLASS_CATALOG:
        return slug
    aliases = {
        "disease": "diseased",
        "diseases": "diseased",
        "cucumber_diseased": "diseased",
        "cucumber_disease": "diseased",
        "powdery_mildew": "powdery_mildew",
        "powdery mildew": "powdery_mildew",
        "downy_mildew": "downy_mildew",
        "downy mildew": "downy_mildew",
        "bacterial_wilt": "bacterial_wilt",
        "bacterial wilt": "bacterial_wilt",
        "leaf_spot": "leaf_spot",
        "leaf spot": "leaf_spot",
        "rust": "leaf_spot",
        "blight": "bacterial_wilt",
        "normal": "healthy",
        "no_disease": "healthy",
    }
    if slug in aliases:
        return aliases[slug]
    for key in CLASS_CATALOG:
        if key in slug or slug in key:
            return key
    if any(x in slug for x in ("healthy", "normal", "ok")):
        return "healthy"
    if any(x in slug for x in ("mildew", "spot", "rust", "blight", "wilt", "rot")):
        if "powdery" in slug:
            return "powdery_mildew"
        if "downy" in slug:
            return "downy_mildew"
        if "bacterial" in slug or "wilt" in slug:
            return "bacterial_wilt"
        if "spot" in slug:
            return "leaf_spot"
        return "diseased"
    if "disease" in slug or slug == "diseased":
        return "diseased"
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
