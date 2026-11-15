"""Gemini's own advice for uncatalogued conditions, and /report + /care reading the named plant's scan.

Gemini is the shared fake SDK from conftest; no network.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from services import analytics_store

GENERIC_TIP = "Capture another angle with better lighting for a clearer diagnosis."


def _jpeg(color=(40, 120, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), color).save(buf, format="JPEG")
    return buf.getvalue()


def _scan(client, color=(40, 120, 60), **data):
    return client.post("/predict", files={"file": ("x.jpg", _jpeg(color), "image/jpeg")}, data={"identify": "true", **data})


# --- advice -------------------------------------------------------------------

def test_uncatalogued_condition_shows_geminis_advice(fastapi_client, fake_gemini):
    fake_gemini.diagnosis["diagnosis"]["primary_condition"] = "Marssonina Leaf Blotch"
    fake_gemini.diagnosis["recommended_action"] = "Remove the spotted leaves and keep the foliage dry."
    body = _scan(fastapi_client).json()
    assert body["disease"] == "Marssonina Leaf Blotch"
    assert body["health"]["recommendation"] == "Remove the spotted leaves and keep the foliage dry."
    assert GENERIC_TIP not in str(body)


def test_catalogued_condition_shows_geminis_advice(fastapi_client, fake_gemini):
    fake_gemini.diagnosis["recommended_action"] = "Gemini says something else."
    body = _scan(fastapi_client).json()
    assert body["disease"] == "Powdery Mildew"
    assert body["health"]["recommendation"] == "Gemini says something else."


def test_geminis_condition_name_is_never_renamed(fastapi_client, fake_gemini):
    fake_gemini.diagnosis["diagnosis"]["primary_condition"] = "Rose Black Spot"
    body = _scan(fastapi_client).json()
    assert body["disease"] == "Rose Black Spot"
    assert body["class_name"] == "leaf_spot"


@pytest.mark.parametrize(
    "status, health_category, category, stress, expected",
    [
        ("healthy", "healthy", "healthy", "none", "healthy"),
        ("diseased", "possible_disease", "fungal", "none", "possible_disease"),
        ("stressed", "possible_water_stress", "environmental_stress", "dehydration_or_sun_stress", "possible_water_stress"),
        ("stressed", "other_problem", "pest", "other_stress", "other_problem"),
        ("uncertain", "possible_disease", "unknown", "unknown", "uncertain"),
        ("not_assessable", None, "unknown", "unknown", "uncertain"),
        # Gemini left health_category empty: read it from its other fields.
        ("stressed", None, "environmental_stress", "dehydration_or_sun_stress", "possible_water_stress"),
        ("diseased", None, "bacterial", "none", "possible_disease"),
    ],
)
def test_scan_carries_the_health_assessment(fastapi_client, fake_gemini, status, health_category, category, stress, expected):
    dx = fake_gemini.diagnosis
    dx["diagnosis"].update(status=status, category=category, primary_condition=None if status in ("uncertain", "not_assessable") else "Some condition")
    if status == "not_assessable":
        dx["image_quality"] = "unusable"
    dx["stress_signal"] = stress
    dx["health_category"] = health_category
    body = _scan(fastapi_client).json()
    assert body["metadata"]["assessment"]["category"] == expected


def test_missing_advice_falls_back_without_failing(fastapi_client, fake_gemini):
    fake_gemini.diagnosis["diagnosis"]["primary_condition"] = "Marssonina Leaf Blotch"
    fake_gemini.diagnosis.pop("recommended_action", None)
    resp = _scan(fastapi_client)
    assert resp.status_code == 200
    assert resp.json()["health"]["recommendation"]


def test_uncertain_scan_keeps_the_retake_guidance(fastapi_client, fake_gemini):
    fake_gemini.diagnosis["diagnosis"]["status"] = "uncertain"
    fake_gemini.diagnosis["recommended_action"] = "Should not be used."
    body = _scan(fastapi_client).json()
    assert body["disease"] == "Unknown"
    assert "scan again" in body["health"]["recommendation"]


# --- report and care use the named plant's scan ---------------------------------

def test_report_uses_the_named_plants_scan_and_identity(fastapi_client, fake_gemini):
    fake_gemini.diagnosis["diagnosis"]["primary_condition"] = "Marssonina Leaf Blotch"
    fake_gemini.diagnosis["plant_identification"].update(common_name="Apple", scientific_name="Malus domestica")
    _scan(fastapi_client, color=(10, 80, 30), plant_id="apple_tree_7", zone_id="zone_beta")
    fake_gemini.diagnosis["diagnosis"]["primary_condition"] = "Powdery Mildew"
    _scan(fastapi_client, color=(90, 20, 20), plant_id="other_plant")  # newer, different plant

    report = fastapi_client.post("/report", json={"plant_id": "apple_tree_7"}).json()
    assert report["disease"] == "Marssonina Leaf Blotch"
    assert report["zone_id"] == "zone_beta"
    assert report["plant"]["common_name"] == "Apple"


def test_care_species_comes_only_from_the_plants_own_scan(fastapi_client, fake_gemini):
    fake_gemini.diagnosis["plant_identification"].update(common_name="Tomato", scientific_name="Solanum lycopersicum")
    _scan(fastapi_client, color=(5, 5, 90))  # no plant_id: must not decide cucumber_001's species
    assert fastapi_client.get("/care/cucumber_001").json()["species_id"] == "cucumber"
    _scan(fastapi_client, color=(5, 90, 5), plant_id="tomato_9")
    assert fastapi_client.get("/care/tomato_9").json()["species_id"] == "tomato"


def test_stored_scan_keeps_only_what_reports_need():
    meta = {"plant_id": "p1", "raw_disease_label": "X", "plant_identification": {"common_name": "A"},
            "gemini_diagnosis": {"big": "x" * 5000}, "image_url": "/uploads/a.jpg"}
    assert analytics_store._report_meta(meta) == {k: meta[k] for k in ("plant_id", "raw_disease_label", "plant_identification")}
    assert analytics_store._report_meta('{"plant_id": "p2"}') == {"plant_id": "p2"}  # Postgres rows store JSON text
    assert analytics_store._report_meta("not json") == {}
