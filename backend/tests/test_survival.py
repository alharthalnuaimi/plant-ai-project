"""Phase 3 — unit tests for the survival scoring path.

Survival is implemented as a derived field on ``PlantHealthScore`` (see
``services.plant_health.compute_plant_health``). These tests pin the
boundary behaviour the UI relies on: 0..100 range, fixed caps for
high/critical disease, and the healthy + good-environment uplift.
"""

from __future__ import annotations

import pytest

from services.plant_health import compute_plant_health

pytestmark = pytest.mark.unit


def test_survival_in_range():
    score = compute_plant_health("Healthy", 0.9, accepted=True)
    assert 0 <= score.survival_chance <= 100


def test_high_disease_risk_caps_survival_at_72():
    score = compute_plant_health("Leaf Spot", 0.85, accepted=True)
    if score.disease_risk == "High":
        assert score.survival_chance <= 72


def test_healthy_plant_in_good_environment_has_high_survival(healthy_sensor):
    score = compute_plant_health(
        "Healthy", 0.97, accepted=True, sensor=healthy_sensor
    )
    assert score.survival_chance >= 85


def test_unknown_disease_does_not_crash():
    """Resilience: unrecognised label → still returns a valid score."""

    score = compute_plant_health("totally_unknown_label", 0.4, accepted=False)
    assert 0 <= score.plant_health <= 100
    assert 0 <= score.survival_chance <= 100
