"""Phase 3 — smoke tests that exercise the FastAPI app end-to-end.

Runs against the in-memory persistence backend (set in conftest.py via
the ``PERSISTENCE_BACKEND=memory`` env var). These tests stand up the
full app + routers and hit endpoints with the standard FastAPI
TestClient — no Docker / Supabase needed.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke


def test_health_root(fastapi_client):
    r = fastapi_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "uptime_sec" in body


def test_health_db_reports_memory_fallback(fastapi_client):
    r = fastapi_client.get("/health/db")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "memory_fallback"
    assert body["postgres_reachable"] is False


def test_health_sensor_returns_offline_when_no_devices(fastapi_client):
    r = fastapi_client.get("/health/sensor")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("offline", "degraded", "healthy")
    assert "devices" in body
    assert "retry_stats" in body
    assert "validation_failures_24h" in body


def test_post_sensor_accepts_valid_payload_and_warms_health(fastapi_client):
    payload = {
        "user_id": "demo_user",
        "zone_id": "zone_alpha",
        "device_id": "esp32_test_smoke",
        "air_temperature": 24.0,
        "air_humidity": 60.0,
        "light_lux": 30000.0,
        "soil_temperature": 22.0,
        "soil_humidity": 65.0,
        "soil_ph": 6.5,
        "soil_ec": 2.0,
    }
    r = fastapi_client.post("/sensor", json=payload)
    assert r.status_code == 200
    assert r.json()["device_id"] == "esp32_test_smoke"

    r = fastapi_client.get("/health/sensor?device_id=esp32_test_smoke")
    assert r.status_code == 200
    devices = r.json()["devices"]
    assert any(d["device_id"] == "esp32_test_smoke" and d["freshness"] == "live" for d in devices)


def test_post_sensor_rejects_invalid_ph(fastapi_client):
    bad = {
        "user_id": "demo_user",
        "zone_id": "zone_alpha",
        "device_id": "esp32_test_smoke",
        "air_temperature": 24,
        "air_humidity": 55,
        "light_lux": 850,
        "soil_temperature": 22,
        "soil_humidity": 42,
        "soil_ph": 99,
        "soil_ec": 1.2,
    }
    r = fastapi_client.post("/sensor", json=bad)
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error"
    # Phase 3: validation_failures_24h must increment.
    h = fastapi_client.get("/health/sensor").json()
    assert h["validation_failures_24h"] >= 1


def test_predict_returns_plant_block(fastapi_client, jpeg_bytes):
    files = {"file": ("leaf.jpg", jpeg_bytes, "image/jpeg")}
    data = {"user_id": "demo_user", "zone_id": "zone_alpha"}
    r = fastapi_client.post("/predict", files=files, data=data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "plant" in body
    assert body["plant"] is not None
    assert body["plant"]["species_id"] in ("cucumber", "tomato", "pepper_bell", "lettuce", "basil", "strawberry")


def test_predict_with_manual_species_id_overrides_stub(fastapi_client, jpeg_bytes):
    files = {"file": ("leaf.jpg", jpeg_bytes, "image/jpeg")}
    data = {"species_id": "tomato"}
    r = fastapi_client.post("/predict", files=files, data=data)
    assert r.status_code == 200
    body = r.json()
    assert body["plant"]["species_id"] == "tomato"
    assert body["plant"]["source"] == "manual"
    assert body["plant"]["confidence"] == 1.0


def test_care_list_species(fastapi_client):
    r = fastapi_client.get("/care")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert "cucumber" in body["species_ids"]


def test_care_static_template(fastapi_client):
    r = fastapi_client.get("/care/species/cucumber")
    assert r.status_code == 200
    body = r.json()
    assert body["species_id"] == "cucumber"
    assert body["scientific_name"] == "Cucumis sativus"


def test_care_unknown_species_falls_back_without_404(fastapi_client):
    r = fastapi_client.get("/care/species/dragonfruit")
    assert r.status_code == 200
    assert r.json()["species_id"] == "cucumber"


def test_care_live_plan(fastapi_client):
    payload = {
        "user_id": "demo_user", "zone_id": "zone_alpha", "device_id": "esp32_test_care",
        "air_temperature": 24, "air_humidity": 60, "light_lux": 30000,
        "soil_temperature": 22, "soil_humidity": 65, "soil_ph": 6.5, "soil_ec": 2.0,
    }
    fastapi_client.post("/sensor", json=payload)
    r = fastapi_client.get("/care/cucumber_001?device_id=esp32_test_care")
    assert r.status_code == 200
    body = r.json()
    assert body["species_id"] == "cucumber"
    assert body["has_sensor_context"] is True
    assert body["source"] == "config+sensor"


def test_report_multipart_image(fastapi_client, jpeg_bytes):
    files = {"file": ("leaf.jpg", jpeg_bytes, "image/jpeg")}
    data = {"plant_id": "cucumber_001"}
    r = fastapi_client.post("/report", files=files, data=data)
    assert r.status_code == 200
    body = r.json()
    assert body["plant_id"] == "cucumber_001"
    for k in ("plant_health", "disease_risk", "stress_level", "survival_chance"):
        assert 0 <= body["scores"][k] <= 100
    for k in ("plant_health", "disease_risk", "stress_level", "survival_chance"):
        assert isinstance(body["explanation"][k], str)
        assert body["explanation"][k]


def test_report_json_body_no_image(fastapi_client):
    body = {"plant_id": "cucumber_001"}
    r = fastapi_client.post("/report", json=body)
    assert r.status_code == 200
    out = r.json()
    assert out["plant_id"] == "cucumber_001"
    assert out["scores"]["survival_chance"] >= 0


def test_report_400_when_no_input(fastapi_client):
    r = fastapi_client.post("/report")
    assert r.status_code == 400
