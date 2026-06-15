"""Phase 3 — unit tests for the care recommendation engine."""

from __future__ import annotations

import pytest

from services.care_engine import build_care_plan, load_template

pytestmark = pytest.mark.unit


def test_load_template_known_species():
    t = load_template("cucumber")
    assert t.species_id == "cucumber"
    assert t.scientific_name == "Cucumis sativus"
    assert t.family == "Cucurbitaceae"
    assert t.temperature_c is not None and len(t.temperature_c) == 2


def test_load_template_unknown_falls_back_to_cucumber():
    t = load_template("dragonfruit")
    assert t.species_id == "cucumber"


def test_load_template_alias_resolution():
    t = load_template("cucumis_sativus")
    assert t.species_id == "cucumber"


def test_plan_without_sensor_is_config_only():
    plan = build_care_plan(species_id="cucumber", sensor=None)
    assert plan.has_sensor_context is False
    assert plan.source == "config"
    assert plan.warnings == []
    assert len(plan.recommendations) >= 1  # at least the static info chips
    assert plan.current_stage is not None


def test_plan_with_healthy_sensor_has_no_warnings(healthy_sensor):
    plan = build_care_plan(species_id="cucumber", sensor=healthy_sensor)
    assert plan.has_sensor_context is True
    assert plan.source == "config+sensor"
    assert plan.warnings == []


def test_plan_with_stressed_sensor_emits_critical_and_warning(stressed_sensor):
    plan = build_care_plan(species_id="cucumber", sensor=stressed_sensor)
    severities = {r.severity for r in plan.warnings}
    assert "critical" in severities
    assert "warning" in severities
    categories = {r.category for r in plan.warnings}
    assert "watering" in categories  # soil_humidity=20 < target 55-75
    assert "soil_ph" in categories  # ph 4.5 < 6.0
    assert all(r.target and r.current for r in plan.warnings)


def test_growth_stage_from_days_since_planted():
    germ = build_care_plan(species_id="cucumber", days_since_planted=2)
    assert germ.current_stage is not None and germ.current_stage.name == "Germination"

    fruit = build_care_plan(species_id="cucumber", days_since_planted=70)
    assert fruit.current_stage is not None
    # Anything past germination is acceptable here — the cucumber YAML lays
    # out ~7+14+35+14+50 = 120 days total, so day 70 should be Flowering or
    # later.
    assert fruit.current_stage.name in ("Flowering", "Fruiting")


def test_plan_includes_static_info_chips_when_template_has_them():
    plan = build_care_plan(species_id="cucumber", sensor=None)
    info_categories = {r.category for r in plan.recommendations if r.severity == "info"}
    assert {"watering", "fertilizer"} <= info_categories
