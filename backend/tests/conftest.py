"""
Phase 3 pytest fixtures.

Tests run with ``PERSISTENCE_BACKEND=memory`` so the entire suite is
self-contained: no Supabase, no Docker, no network. Tests that *need*
Postgres (marked ``@pytest.mark.db``) are skipped unless ``DATABASE_URL``
is supplied via the environment.
"""

from __future__ import annotations

import io
import os
import sys
import warnings
from pathlib import Path

import pytest
from PIL import Image

# Force memory persistence before any backend module is imported.
os.environ.setdefault("PERSISTENCE_BACKEND", "memory")
os.environ.setdefault("YOLO_WEIGHTS_PATH", "")  # disable real YOLO
os.environ.setdefault("PERSIST_EVENTS", "false")

# Make `backend/` importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

warnings.filterwarnings("ignore", category=DeprecationWarning)


@pytest.fixture(scope="session")
def jpeg_bytes() -> bytes:
    """Tiny RGB JPEG that the stub vision predictor + plant ID accept."""

    img = Image.new("RGB", (96, 96), color=(40, 110, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


@pytest.fixture(scope="session")
def healthy_sensor():
    from schemas.sensors import SensorReading, SensorStatus

    status = SensorStatus(
        air_temperature_status="normal",
        air_humidity_status="normal",
        light_status="normal",
        soil_temperature_status="normal",
        soil_humidity_status="normal",
        ph_status="normal",
        ec_status="normal",
        overall_environment_status="healthy",
    )
    return SensorReading(
        user_id="demo_user",
        zone_id="zone_alpha",
        device_id="esp32_001",
        air_temperature=24.0,
        air_humidity=60.0,
        light_lux=30000.0,
        soil_temperature=22.0,
        soil_humidity=65.0,
        soil_ph=6.5,
        soil_ec=2.0,
        timestamp="2026-06-02T13:00:00+00:00",
        status=status,
    )


@pytest.fixture(scope="session")
def stressed_sensor():
    from schemas.sensors import SensorReading, SensorStatus

    status = SensorStatus(
        air_temperature_status="hot",
        air_humidity_status="dry",
        light_status="low",
        soil_temperature_status="hot",
        soil_humidity_status="dry",
        ph_status="acidic",
        ec_status="low",
        overall_environment_status="stressed",
    )
    return SensorReading(
        user_id="demo_user",
        zone_id="zone_alpha",
        device_id="esp32_001",
        air_temperature=36.0,
        air_humidity=30.0,
        light_lux=8000.0,
        soil_temperature=28.0,
        soil_humidity=20.0,
        soil_ph=4.5,
        soil_ec=0.5,
        timestamp="2026-06-02T13:00:00+00:00",
        status=status,
    )


@pytest.fixture()
def fastapi_client():
    """Boot the FastAPI app once per test, with the TestClient."""

    from fastapi.testclient import TestClient

    from main import app

    with TestClient(app) as client:
        yield client
