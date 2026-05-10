"""
Weighted rule-based survival (MVP). Llama may *describe* this score but must not replace it.
Weights: disease 40%, soil moisture 25%, temperature 20%, humidity 15%.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import numpy as np
from services.config_loader import get_runtime_config


@dataclass
class SurvivalInputs:
    disease: str
    disease_confidence: float
    stress_hint: str
    soil_moisture: float  # 0-100 percent
    temperature_c: float
    humidity_pct: float  # 0-100
    species: str | None = None


def _disease_component(disease: str, confidence: float) -> float:
    """
    Returns 0..1 where 1 = best for survival (low impact).
    Penalize known bad labels and scale by model confidence.
    """
    d = (disease or "").strip().lower()
    healthy = {"healthy", "no disease", "none", "background"}
    severe = {"blight", "rust", "rot", "canker", "mold", "mildew", "spot", "wilt"}

    if d in healthy or "healthy" in d:
        base = 0.95
    elif any(k in d for k in severe):
        base = 0.35
    elif d in {"", "unknown"}:
        base = 0.70
    else:
        base = 0.55

    # High confidence on a bad class hurts more; high confidence on healthy helps
    c = float(np.clip(confidence, 0.0, 1.0))
    if base >= 0.9:
        return float(np.clip(0.75 + 0.25 * c, 0.0, 1.0))
    impact = base * (1.0 - 0.35 * c)
    return float(np.clip(impact, 0.0, 1.0))


def _moisture_score(pct: float) -> float:
    """Optimal band ~40–70% for prototype."""
    x = float(np.clip(pct, 0.0, 100.0))
    if 40 <= x <= 70:
        return 1.0
    if x < 40:
        return float(np.clip(x / 40.0, 0.0, 1.0))
    # too wet
    over = x - 70
    return float(np.clip(1.0 - over / 50.0, 0.2, 1.0))


def _temperature_score(temp_c: float) -> float:
    t = float(temp_c)
    # Comfortable band 18–28°C
    if 18 <= t <= 28:
        return 1.0
    if t < 18:
        return float(np.clip(0.35 + (t / 18.0) * 0.65, 0.0, 1.0))
    # hot
    excess = t - 28
    return float(np.clip(1.0 - excess / 18.0, 0.15, 1.0))


def _humidity_score(h: float) -> float:
    x = float(np.clip(h, 0.0, 100.0))
    # 45–65% generally kind to many foliage plants (prototype)
    if 45 <= x <= 65:
        return 1.0
    if x < 45:
        return float(np.clip(0.35 + x / 45.0 * 0.65, 0.0, 1.0))
    # very high humidity — fungal risk (light penalty)
    over = x - 65
    return float(np.clip(1.0 - over / 70.0, 0.35, 1.0))


def _stress_hint_adjustment(hint: str) -> float:
    h = (hint or "").lower()
    if "dehydration" in h or "sun_stress" in h:
        return -0.05
    if "yellowing" in h or "low_vigor" in h:
        return -0.04
    return 0.0


def _species_component(species: str | None) -> float:
    """
    Species sensitivity factor for future ML migration.
    1.0 means neutral; lower means we apply mild conservatism.
    """
    if not species:
        return 1.0
    s = species.strip().lower()
    # Lightweight configurable knobs; can migrate to registry/config DB later.
    high_sensitivity = {"basil", "lettuce", "fern"}
    robust = {"aloe", "cactus", "snake_plant", "dracaena"}
    if any(k in s for k in high_sensitivity):
        return 0.92
    if any(k in s for k in robust):
        return 1.03
    return 1.0


def _weights() -> dict[str, float]:
    # Keep MVP defaults, prefer YAML config, allow env override for quick tests.
    cfg = get_runtime_config().get("survival", {}).get("weights", {})
    return {
        "disease": float(os.getenv("SURVIVAL_WEIGHT_DISEASE", cfg.get("disease", 0.40))),
        "soil_moisture": float(
            os.getenv("SURVIVAL_WEIGHT_SOIL_MOISTURE", cfg.get("soil_moisture", 0.25))
        ),
        "temperature": float(
            os.getenv("SURVIVAL_WEIGHT_TEMPERATURE", cfg.get("temperature", 0.20))
        ),
        "humidity": float(os.getenv("SURVIVAL_WEIGHT_HUMIDITY", cfg.get("humidity", 0.15))),
    }


def compute_survival(inp: SurvivalInputs) -> dict[str, Any]:
    weights = _weights()
    w_dis = weights["disease"]
    w_moist = weights["soil_moisture"]
    w_temp = weights["temperature"]
    w_hum = weights["humidity"]

    s_dis = _disease_component(inp.disease, inp.disease_confidence)
    s_moist = _moisture_score(inp.soil_moisture)
    s_temp = _temperature_score(inp.temperature_c)
    s_hum = _humidity_score(inp.humidity_pct)
    species_factor = _species_component(inp.species)
    stress_adj = _stress_hint_adjustment(inp.stress_hint)

    combined = (
        w_dis * s_dis + w_moist * s_moist + w_temp * s_temp + w_hum * s_hum
    )
    combined *= species_factor
    combined += stress_adj
    survival = float(np.clip(combined, 0.05, 0.99))

    return {
        "survival_probability": round(survival, 4),
        "breakdown": {
            "disease_component": round(s_dis, 4),
            "moisture_component": round(s_moist, 4),
            "temperature_component": round(s_temp, 4),
            "humidity_component": round(s_hum, 4),
            "species_component": round(species_factor, 4),
            "stress_component": round(stress_adj, 4),
        },
        "weights": weights,
        "policy_version": "rule_based_v2",
    }
