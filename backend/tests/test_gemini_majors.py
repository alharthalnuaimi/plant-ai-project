"""Gemini-era fixes: condition names kept, provider test off the event loop, input size limits.

Gemini is replaced by the shared fake SDK from conftest; no network.
"""

from __future__ import annotations

import asyncio
import copy
import json
import time

import httpx
import pytest

from services.survival import _disease_component
from tests.gemini_fakes import DEFAULT_DIAGNOSIS


def _scan(client, jpeg_bytes, **data):
    return client.post("/predict", files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")}, data={"identify": "false", **data})


# --- condition names ----------------------------------------------------------

@pytest.mark.parametrize("condition", ["Anthracnose", "Spider mite damage", "Nitrogen deficiency"])
def test_condition_outside_the_catalog_keeps_its_name(fastapi_client, jpeg_bytes, fake_gemini, condition):
    fake_gemini.diagnosis["diagnosis"]["primary_condition"] = condition

    resp = _scan(fastapi_client, jpeg_bytes)
    assert resp.status_code == 200, resp.text
    assert resp.json()["disease"] == condition

    assert fastapi_client.get("/scans/history?limit=1").json()["scans"][0]["disease"] == condition
    assert fastapi_client.get("/analytics/history?limit=1").json()[0]["disease"] == condition


def test_survival_score_uses_the_condition_name(fastapi_client, jpeg_bytes, fake_gemini):
    fake_gemini.diagnosis["diagnosis"]["primary_condition"] = "Anthracnose"
    resp = fastapi_client.post(
        "/analyze",
        files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")},
        data={"soil_moisture": "50", "temperature": "25", "humidity": "60"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["vision"]["disease"] == "Anthracnose"
    expected = round(_disease_component("Anthracnose", body["vision"]["confidence"]), 4)
    assert body["survival"]["breakdown"]["disease_component"] == expected
    assert expected != round(_disease_component("Unknown", body["vision"]["confidence"]), 4)


def test_catalog_conditions_keep_geminis_name_and_get_the_catalog_class(fastapi_client, jpeg_bytes, fake_gemini):
    fake_gemini.diagnosis["diagnosis"]["primary_condition"] = "powdery mildew (early stage)"
    body = _scan(fastapi_client, jpeg_bytes).json()
    assert body["disease"] == "powdery mildew (early stage)"
    assert body["class_name"] == "powdery_mildew"


@pytest.mark.parametrize("status", ["uncertain", "not_assessable"])
def test_no_diagnosis_is_still_unknown(fastapi_client, jpeg_bytes, fake_gemini, status):
    fake_gemini.diagnosis["diagnosis"]["status"] = status
    assert _scan(fastapi_client, jpeg_bytes).json()["disease"] == "Unknown"


# --- provider test does not block --------------------------------------------

@pytest.fixture
def slow_gemini_agent(monkeypatch):
    from services.providers.multi_provider import GeminiAgent

    def slow(self, image_bytes, context_label=""):
        time.sleep(1.0)  # a blocking SDK call
        return {"provider": self.name, "class_label": "Rust", "confidence": 0.8, "bbox": None, "reasoning": "", "status": "success"}

    monkeypatch.setattr(GeminiAgent, "annotate", slow)


async def test_provider_test_does_not_block_other_requests(slow_gemini_agent):
    from main import app

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        t0 = time.perf_counter()  # from the start, so a blocked loop shows up as delay

        async def health_after_start():
            await asyncio.sleep(0.1)
            resp = await client.get("/health")
            return resp.status_code, time.perf_counter() - t0

        test_resp, (health_status, health_seconds) = await asyncio.gather(
            client.post("/admin/providers/test", json={"provider_name": "GEMINI_API_KEY"}),
            health_after_start(),
        )
    assert health_status == 200
    assert health_seconds < 0.6  # answered while the 1 s provider call was still running
    assert test_resp.json()["test_result"]["status"] == "success"


async def test_provider_test_times_out(slow_gemini_agent, monkeypatch):
    from main import app
    from routes import admin_providers

    monkeypatch.setattr(admin_providers, "PROVIDER_TEST_TIMEOUT_S", 0.2)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        t0 = time.perf_counter()
        resp = await client.post("/admin/providers/test", json={"provider_name": "GEMINI_API_KEY"})
    assert time.perf_counter() - t0 < 0.9
    assert resp.status_code == 200
    assert resp.json()["test_result"]["status"] == "error"


# --- size limits --------------------------------------------------------------

VISION = {"disease": "Rust", "confidence": 0.8}


def _chat(client, **body):
    return client.post("/chat", json={"vision": VISION, **body})


def test_chat_question_length(fastapi_client):
    assert _chat(fastapi_client, user_question="x" * 2000).status_code == 200
    assert _chat(fastapi_client, user_question="x" * 2001).status_code == 422


def test_chat_species_length(fastapi_client):
    assert _chat(fastapi_client, sensors={"species": "x" * 101}).status_code == 422


@pytest.mark.parametrize(("field", "limit"), [("user_question", 2000), ("species", 100)])
def test_analyze_field_lengths(fastapi_client, jpeg_bytes, field, limit):
    def analyze(value):
        return fastapi_client.post(
            "/analyze",
            files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")},
            data={"soil_moisture": "50", "temperature": "25", "humidity": "60", field: value},
        )

    assert analyze("x" * limit).status_code == 200
    assert analyze("x" * (limit + 1)).status_code == 422


def test_species_id_length(fastapi_client, jpeg_bytes):
    assert _scan(fastapi_client, jpeg_bytes, species_id="x" * 101).status_code == 422
    files = {"file": ("x.jpg", jpeg_bytes, "image/jpeg")}
    assert fastapi_client.post("/report", files=files, data={"species_id": "x" * 101}).status_code == 422
    assert fastapi_client.post("/report", json={"plant_id": "p", "species_id": "x" * 101}).status_code == 422


def _reasoning_prompt(fake_gemini):
    return str(fake_gemini.calls_for("GeminiReasoning")[-1]["contents"])


def test_valid_diagnosis_reaches_the_prompt(fastapi_client, fake_gemini):
    diagnosis = copy.deepcopy(DEFAULT_DIAGNOSIS)
    diagnosis["diagnosis"]["primary_condition"] = "MARKER_CONDITION"
    resp = _chat(fastapi_client, vision={**VISION, "metadata": {"gemini_diagnosis": diagnosis}})
    assert resp.status_code == 200, resp.text
    assert "MARKER_CONDITION" in _reasoning_prompt(fake_gemini)


def test_diagnosis_in_the_wrong_shape_is_dropped(fastapi_client, fake_gemini):
    resp = _chat(fastapi_client, vision={**VISION, "metadata": {"gemini_diagnosis": {"note": "MARKER_EXTRA"}}})
    assert resp.status_code == 200, resp.text
    assert "MARKER_EXTRA" not in _reasoning_prompt(fake_gemini)


def test_oversized_diagnosis_is_dropped(fastapi_client, fake_gemini):
    diagnosis = copy.deepcopy(DEFAULT_DIAGNOSIS)
    diagnosis["summary"] = "MARKER_BIG " + "x" * 25_000
    resp = _chat(fastapi_client, vision={**VISION, "metadata": {"gemini_diagnosis": diagnosis}})
    assert resp.status_code == 200, resp.text
    assert "MARKER_BIG" not in _reasoning_prompt(fake_gemini)


def test_oversized_chat_request_is_rejected_before_gemini(fastapi_client, fake_gemini):
    resp = _chat(fastapi_client, vision={**VISION, "disease": "x" * 70_000})
    assert resp.status_code == 413
    assert fake_gemini.calls_for("GeminiReasoning") == []
    assert json.loads(resp.text)  # still a normal JSON error body
