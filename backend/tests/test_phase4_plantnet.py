"""
Unit tests for Phase 4 PlantNet status & health reporting.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from main import app
from models.plant_id_model import PlantNetPredictor


def test_health_services_endpoint():
    client = TestClient(app)
    response = client.get("/health/services")
    assert response.status_code == 200

    data = response.json()
    assert "plantnet_status" in data
    assert "plantnet_key_present" in data
    assert "gemini_status" in data
    assert "yolo_status" in data


def test_plantnet_predictor_stub_fallback():
    predictor = PlantNetPredictor(api_key="")
    # Image must be valid
    from PIL import Image
    import io
    img = Image.new("RGB", (100, 100), color=(0, 200, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    
    pred = predictor.predict(buf.getvalue())
    assert pred.source == "stub"
    assert pred.species_id is not None
