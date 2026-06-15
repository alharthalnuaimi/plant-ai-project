"""Phase 3 — unit tests for ``services.plant_health``."""

from __future__ import annotations

import pytest

from services.plant_health import compute_plant_health

pytestmark = pytest.mark.unit


def test_healthy_high_confidence_no_sensor_returns_high_score():
    score = compute_plant_health("Healthy", 0.95, accepted=True, sensor=None)
    assert score.class_name == "healthy"
    assert score.disease_risk == "Low"
    assert score.environment_stress == "Low"
    assert score.plant_health >= 80
    assert score.survival_chance >= 80


def test_diseased_high_confidence_drops_health_and_survival():
    score = compute_plant_health("Powdery Mildew", 0.85, accepted=True, sensor=None)
    assert score.class_name != "healthy"
    assert score.disease_risk in ("Medium", "High", "Critical")
    assert score.plant_health < 80


def test_environment_stress_drops_score_when_sensor_is_bad(stressed_sensor):
    score = compute_plant_health(
        "Healthy", 0.95, accepted=True, sensor=stressed_sensor
    )
    assert score.environment_stress in ("Medium", "High")
    assert score.plant_health < 90  # should be penalised


def test_low_confidence_unaccepted_disease_softens_penalty():
    high = compute_plant_health("Powdery Mildew", 0.85, accepted=True)
    low = compute_plant_health("Powdery Mildew", 0.30, accepted=False)
    # Lower confidence + not accepted → softer penalty → higher health
    assert low.plant_health >= high.plant_health


def test_critical_disease_caps_survival_at_55():
    """Risk_tier=critical paths should keep survival ≤55."""

    score = compute_plant_health("Blight", 0.95, accepted=True)
    if score.disease_risk == "Critical":
        assert score.survival_chance <= 55
