"""Rule-based plant health score (MVP, no DB)."""

from __future__ import annotations

from typing import Any

from schemas.health import PlantHealthScore
from schemas.sensors import SensorReading
from services.disease_taxonomy import classify_disease

_RISK_TO_DISEASE = {
    "low": "Low",
    "medium": "Medium",
    "high": "High",
    "critical": "Critical",
}


def _environment_stress(reading: SensorReading | None) -> tuple[str, int]:
    """Returns (Low|Medium|High, penalty 0-35)."""
    if reading is None:
        return "Low", 5
    penalty = 0
    if reading.air_humidity < 35:
        penalty += 12
    elif reading.air_humidity < 45:
        penalty += 6
    if reading.soil_humidity < 28:
        penalty += 12
    elif reading.soil_humidity < 38:
        penalty += 5
    if reading.air_temperature > 32:
        penalty += 10
    elif reading.air_temperature > 28:
        penalty += 4
    if reading.soil_ph < 5.5 or reading.soil_ph > 7.8:
        penalty += 8
    if penalty >= 18:
        return "High", penalty
    if penalty >= 8:
        return "Medium", penalty
    return "Low", penalty


def _disease_penalty(class_name: str, confidence: float, accepted: bool) -> int:
    tier = classify_disease(class_name)["risk_tier"]
    conf = max(0.0, min(1.0, float(confidence)))
    base = {"low": 0, "medium": 18, "high": 32, "critical": 48}.get(tier, 22)
    if class_name == "healthy":
        return max(0, int((1.0 - conf) * 8))
    scale = 0.55 + conf * 0.45
    if not accepted:
        scale *= 0.75
    return min(55, int(base * scale))


def compute_plant_health(
    disease: str,
    confidence: float,
    *,
    accepted: bool = True,
    sensor: SensorReading | None = None,
    source: str = "live",
) -> PlantHealthScore:
    tax = classify_disease(disease)
    class_name = tax["class_name"]
    env_label, env_penalty = _environment_stress(sensor)
    dis_penalty = _disease_penalty(class_name, confidence, accepted)

    plant_health = max(5, min(98, 92 - dis_penalty - env_penalty))
    if class_name == "healthy" and env_label == "Low":
        plant_health = max(plant_health, int(78 + confidence * 20))

    disease_risk = _RISK_TO_DISEASE.get(tax["risk_tier"], "Medium")
    if class_name == "healthy":
        disease_risk = "Low" if confidence >= 0.6 else "Medium"

    survival = max(10, min(99, plant_health + (8 if class_name == "healthy" else -6)))
    if disease_risk == "Critical":
        survival = min(survival, 55)
    elif disease_risk == "High":
        survival = min(survival, 72)

    rec = tax["default_recommendation"]
    if env_label == "High" and class_name == "healthy":
        rec = "Environment stress detected — check humidity, soil moisture, and temperature."
    elif env_label == "High":
        rec = rec + " Also address environment stress (humidity, soil moisture, or temperature)."

    return PlantHealthScore(
        plant_health=int(round(plant_health)),
        disease_risk=disease_risk,  # type: ignore[arg-type]
        environment_stress=env_label,  # type: ignore[arg-type]
        survival_chance=int(round(survival)),
        recommendation=rec.strip(),
        class_name=class_name,
        disease_type=tax["disease_type"],
        source=source if source in ("live", "demo", "baseline") else "live",  # type: ignore[arg-type]
    )


def enrich_vision_result(
    result: "VisionResult",
    user_id: str,
    zone_id: str,
    device_id: str = "esp32_001",
) -> "VisionResult":
    from schemas.contracts import VisionResult
    from services import sensor_store
    from services.disease_taxonomy import classify_disease

    raw_label = (result.metadata or {}).get("raw_disease_label") or result.disease
    tax = classify_disease(raw_label)
    try:
        sensor = sensor_store.get_latest(user_id, zone_id, device_id)
    except Exception:
        sensor = None
    src = "demo" if sensor and getattr(sensor, "source", "") == "demo" else "live"
    if sensor is None:
        src = "baseline"
    health = compute_plant_health(
        raw_label,
        float(result.confidence),
        accepted=result.accepted,
        sensor=sensor,
        source=src,
    )
    meta = dict(result.metadata or {})
    meta.setdefault("raw_disease_label", raw_label)
    return result.model_copy(
        update={
            "disease": tax["display_label"],
            "class_name": tax["class_name"],
            "disease_type": tax["disease_type"],
            "health": health,
            "metadata": meta,
        }
    )


def compute_from_scan_record(scan: dict[str, Any], sensor: SensorReading | None) -> PlantHealthScore:
    return compute_plant_health(
        scan.get("disease", "unknown"),
        float(scan.get("confidence", 0)),
        accepted=bool(scan.get("accepted", True)),
        sensor=sensor,
        source="live",
    )
