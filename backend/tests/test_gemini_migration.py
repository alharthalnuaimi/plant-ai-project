"""Gemini-only AI architecture: client, diagnosis, reasoning, errors, routes.

Every test runs against the ``FakeGenai`` SDK installed by conftest, so no
request leaves the machine and no API quota is used.
"""

from __future__ import annotations

import copy
import io
import json
import logging
import sys

import httpx
import pytest
from fastapi.testclient import TestClient
from google.genai import errors as genai_errors
from PIL import Image

from main import app
from routes import predict as predict_route
from services import sensor_store
from services.gemini import client as gclient
from services.gemini.config import load_gemini_config
from services.gemini.diagnosis import diagnose_plant_image
from services.gemini.errors import (
    GeminiInvalidResponse,
    GeminiNotConfigured,
    ImageTooLargeError,
    InvalidImageError,
)
from services.gemini.schemas import GeminiDiagnosis, enforce_diagnosis_consistency
from tests.conftest import FAKE_GEMINI_KEY
from tests.gemini_fakes import DEFAULT_DIAGNOSIS, make_response


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _jpeg(size=(400, 300), color=(40, 110, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _api_error(code: int, message: str, status: str = "", details: list | None = None):
    body = {"error": {"code": code, "message": message, "status": status}}
    if details:
        body["error"]["details"] = details
    cls = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return cls(code, body)


@pytest.fixture
def client(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(predict_route, "UPLOAD_DIR", uploads)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _predict(client, image=None, **data):
    return client.post(
        "/predict",
        files={"file": ("leaf.jpg", image or _jpeg(), "image/jpeg")},
        data=data,
    )


# --------------------------------------------------------------------------
# 1. client initialisation
# --------------------------------------------------------------------------


def test_client_is_built_from_the_single_key_with_timeout_and_no_sdk_retries(fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_TIMEOUT_SECONDS", "12")
    c = gclient.get_gemini_client()
    assert c.config.api_key == FAKE_GEMINI_KEY
    built = fake_gemini.clients_built[-1]
    assert built["api_key"] == FAKE_GEMINI_KEY
    assert built["http_options"].timeout == 12000
    assert built["http_options"].retry_options.attempts == 1
    # One shared instance for both diagnosis and reasoning.
    assert gclient.get_gemini_client() is c


def test_diagnosis_and_reasoning_models_are_configurable(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-base")
    monkeypatch.setenv("GEMINI_REASONING_MODEL", "gemini-think")
    cfg = load_gemini_config()
    assert cfg.diagnosis_model == "gemini-base"
    assert cfg.reasoning_model == "gemini-think"


def test_api_key_never_appears_in_config_repr_or_status(client):
    cfg = load_gemini_config()
    assert FAKE_GEMINI_KEY not in repr(cfg)
    assert FAKE_GEMINI_KEY not in json.dumps(cfg.public_summary())
    for path in ("/health/services", "/models/health"):
        assert FAKE_GEMINI_KEY not in client.get(path).text


# --------------------------------------------------------------------------
# 2. missing API key
# --------------------------------------------------------------------------


def test_missing_key_raises_not_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    with pytest.raises(GeminiNotConfigured):
        gclient.get_gemini_client()


@pytest.mark.parametrize("call", ["predict", "chat", "analyze"])
def test_missing_key_gives_clear_503_on_every_ai_route(client, monkeypatch, fake_gemini, call):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    if call == "predict":
        resp = _predict(client)
    elif call == "chat":
        resp = client.post("/chat", json={"user_question": "How is my plant?"})
    else:
        resp = client.post(
            "/analyze",
            files={"file": ("x.jpg", _jpeg(), "image/jpeg")},
            data={"soil_moisture": "50", "temperature": "25", "humidity": "60"},
        )
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "gemini_not_configured"
    assert "GEMINI_API_KEY" in body["message"]
    assert fake_gemini.calls == []


# --------------------------------------------------------------------------
# 3. successful diagnosis
# --------------------------------------------------------------------------


def test_predict_maps_gemini_diagnosis_onto_the_existing_contract(client, fake_gemini):
    resp = _predict(client, user_id="demo_user", zone_id="zone_alpha")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["disease"] == "Powdery Mildew"
    assert body["class_name"] == "powdery_mildew"
    assert body["confidence"] == 0.82
    assert body["accepted"] is True
    assert body["model_name"] == "gemini"
    assert body["model_version"].startswith("gemini-3.5-flash/")
    assert body["plant"] == {
        "species_id": "cucumber",
        "common_name": "Cucumber",
        "scientific_name": "Cucumis sativus",
        "family": "Cucurbitaceae",
        "genus": "Cucumis",
        "confidence": 0.9,
        "source": "gemini",
    }
    assert body["gemini_agrees"] is None  # no "disagreement" banner any more
    meta = body["metadata"]
    assert meta["raw_disease_label"] == "Powdery Mildew"
    assert meta["confidence_kind"] == "model_self_reported"
    assert meta["gemini_diagnosis"]["observations"][0]["certainty"] == "confirmed"
    assert meta["gemini"]["call"]["total_tokens"] == 200
    assert body["health"]["recommendation"]

    call = fake_gemini.calls_for("GeminiDiagnosis")[0]
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].system_instruction


def test_image_is_compressed_to_jpeg_before_sending(client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_MAX_IMAGE_SIDE", "512")
    big_png = io.BytesIO()
    Image.new("RGB", (2000, 1000), (20, 140, 40)).save(big_png, format="PNG")
    resp = client.post("/predict", files={"file": ("leaf.png", big_png.getvalue(), "image/png")})
    assert resp.status_code == 200, resp.text
    part = fake_gemini.calls_for("GeminiDiagnosis")[0]["contents"][0]
    assert part.inline_data.mime_type == "image/jpeg"
    sent = Image.open(io.BytesIO(part.inline_data.data))
    assert sent.format == "JPEG" and max(sent.size) == 512
    assert resp.json()["metadata"]["gemini"]["image"]["original_size"] == [2000, 1000]


def test_manual_species_is_a_hint_and_echoed_back(client, fake_gemini):
    body = _predict(client, species_id="tomato").json()
    assert body["plant"]["species_id"] == "tomato" and body["plant"]["source"] == "manual"
    prompt = fake_gemini.calls_for("GeminiDiagnosis")[0]["contents"][1]
    assert "Tomato" in prompt


def test_identify_false_omits_the_plant_block(client):
    assert _predict(client, identify="false").json()["plant"] is None


def test_same_image_is_not_sent_twice(client, fake_gemini):
    image = _jpeg()
    assert _predict(client, image).status_code == 200
    second = _predict(client, image).json()
    assert len(fake_gemini.calls_for("GeminiDiagnosis")) == 1
    assert second["metadata"]["gemini"]["cached"] is True
    # A different hint is a different question → a new request.
    _predict(client, image, species_id="rose")
    assert len(fake_gemini.calls_for("GeminiDiagnosis")) == 2


def test_cache_can_be_disabled(client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_CACHE_TTL_SECONDS", "0")
    image = _jpeg()
    _predict(client, image)
    _predict(client, image)
    assert len(fake_gemini.calls_for("GeminiDiagnosis")) == 2


# --------------------------------------------------------------------------
# honesty: uncertain / not a plant / blurry
# --------------------------------------------------------------------------


def test_not_a_plant_is_reported_and_never_diagnosed(client, fake_gemini):
    d = copy.deepcopy(DEFAULT_DIAGNOSIS)
    d["image_quality"] = "good"
    d["plant_identification"]["is_plant"] = False  # model still (wrongly) filled a disease in
    fake_gemini.diagnosis = d
    body = _predict(client).json()
    assert body["accepted"] is False
    assert body["confidence"] == 0.0
    assert body["plant"] is None
    assert body["metadata"]["raw_disease_label"] == "Not assessable"
    assert body["metadata"]["gemini_diagnosis"]["diagnosis"]["primary_condition"] is None
    assert "No plant could be recognised" in body["health"]["recommendation"]


def test_unusable_image_returns_retake_guidance(client, fake_gemini):
    d = copy.deepcopy(DEFAULT_DIAGNOSIS)
    d["image_quality"] = "unusable"
    d["image_quality_notes"] = "The photo is very blurry."
    fake_gemini.diagnosis = d
    body = _predict(client).json()
    assert body["accepted"] is False
    assert body["metadata"]["diagnosis_status"] == "not_assessable"
    assert "blurry" in body["health"]["recommendation"]


def test_uncertain_diagnosis_does_not_invent_a_condition(client, fake_gemini):
    d = copy.deepcopy(DEFAULT_DIAGNOSIS)
    d["diagnosis"].update({"status": "uncertain", "primary_condition": "Rust", "confidence": 0.3})
    fake_gemini.diagnosis = d
    body = _predict(client).json()
    assert body["metadata"]["raw_disease_label"] == "Uncertain"
    assert body["accepted"] is False
    assert body["metadata"]["gemini_diagnosis"]["diagnosis"]["primary_condition"] is None


def test_consistency_rules_only_remove_claims():
    d = GeminiDiagnosis.model_validate(DEFAULT_DIAGNOSIS)
    assert enforce_diagnosis_consistency(d) == d
    raw = copy.deepcopy(DEFAULT_DIAGNOSIS)
    raw["diagnosis"]["primary_condition"] = "  "
    fixed = enforce_diagnosis_consistency(GeminiDiagnosis.model_validate(raw))
    assert fixed.diagnosis.status == "uncertain" and fixed.diagnosis.primary_condition is None


# --------------------------------------------------------------------------
# 4. successful reasoning + 9. sensor context integration
# --------------------------------------------------------------------------


def test_chat_returns_gemini_reasoning(client, fake_gemini):
    scan = _predict(client).json()
    resp = client.post(
        "/chat",
        json={
            "vision": scan,
            "sensors": {"soil_moisture": 40, "temperature": 26, "humidity": 85, "species": "cucumber"},
            "user_question": "What should I do?",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "gemini"
    assert body["reply"] == fake_gemini.reasoning["answer"]
    assert body["recommendation"] == "Remove the worst affected leaves."
    assert body["reasoning"]["urgency"] == "moderate"
    assert body["reasoning"]["recovery_assessment"]["estimate"] == "good"
    assert 0 <= body["survival_probability"] <= 1

    ctx = json.loads(fake_gemini.calls_for("GeminiReasoning")[0]["contents"][-1].split("\n", 1)[1])
    assert ctx["diagnosis"]["diagnosis"]["primary_condition"] == "Powdery Mildew"
    assert ctx["sensors"]["air_humidity"] == 85.0
    assert ctx["user_question"] == "What should I do?"


def test_chat_never_invents_missing_sensor_values(client, fake_gemini):
    resp = client.post("/chat", json={"user_question": "How do I care for basil?"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["survival_probability"] is None
    ctx = json.loads(fake_gemini.calls_for("GeminiReasoning")[0]["contents"][-1].split("\n", 1)[1])
    assert all(ctx["sensors"][k] is None for k in ("air_temperature", "soil_ph", "soil_ec", "light_lux"))
    assert ctx["diagnosis"] is None


def test_chat_uses_the_latest_device_reading_with_all_sensors(client, fake_gemini):
    reading = {
        "device_id": "esp32_ctx", "zone_id": "zone_ctx", "user_id": "u_ctx",
        "air_temperature": 31.5, "air_humidity": 88, "light_lux": 12000,
        "soil_temperature": 24.5, "soil_humidity": 33, "soil_ph": 5.4, "soil_ec": 1.7,
    }
    assert client.post("/sensor", json=reading).status_code == 200
    resp = client.post(
        "/chat",
        json={
            "user_question": "Why are the leaves curling?",
            "user_id": "u_ctx", "zone_id": "zone_ctx", "device_id": "esp32_ctx",
            "sensors": {"temperature": 10},  # stale client value must lose to the device
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["sensor_context"]["source"] == "device"
    sensors = json.loads(fake_gemini.calls_for("GeminiReasoning")[0]["contents"][-1].split("\n", 1)[1])["sensors"]
    assert sensors["air_temperature"] == 31.5
    assert sensors["soil_ph"] == 5.4 and sensors["soil_ec"] == 1.7
    assert sensors["soil_temperature"] == 24.5 and sensors["light_lux"] == 12000
    assert sensors["age_seconds"] is not None


def test_reasoning_is_never_cached(client, fake_gemini):
    for _ in range(2):
        client.post("/chat", json={"user_question": "hi"})
    assert len(fake_gemini.calls_for("GeminiReasoning")) == 2


def test_predict_snapshots_sensor_reading(client, fake_gemini):
    client.post("/sensor", json={"device_id": "esp32_001", "air_temperature": 22, "air_humidity": 55, "soil_ph": 6.4})
    body = _predict(client).json()
    assert body["metadata"]["sensor_snapshot"]["air_temperature"] == 22


def test_analyze_uses_gemini_for_both_steps(client, fake_gemini):
    resp = client.post(
        "/analyze",
        files={"file": ("x.jpg", _jpeg(), "image/jpeg")},
        data={"soil_moisture": "50", "temperature": "25", "humidity": "60", "user_question": "Is it serious?"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["llm_source"] == "gemini"
    assert body["llama_explanation"] == fake_gemini.reasoning["answer"]
    assert body["reasoning"]["summary"]
    assert len(fake_gemini.calls_for("GeminiDiagnosis")) == 1
    reasoning_call = fake_gemini.calls_for("GeminiReasoning")[0]
    assert reasoning_call["contents"][0].inline_data.mime_type == "image/jpeg"  # photo goes along


# --------------------------------------------------------------------------
# 5. invalid images
# --------------------------------------------------------------------------


def test_corrupt_image_is_400_without_calling_gemini(client, fake_gemini):
    resp = client.post("/predict", files={"file": ("x.jpg", b"notanimage" * 50, "image/jpeg")})
    assert resp.status_code == 400
    assert fake_gemini.calls == []


def test_tiny_image_is_rejected(client, fake_gemini):
    resp = _predict(client, _jpeg(size=(10, 10)))
    assert resp.status_code == 400
    assert resp.json()["error"] == "invalid_image"
    assert fake_gemini.calls == []


def test_oversized_upload_is_413(client, fake_gemini, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "2048")
    resp = _predict(client, _jpeg(size=(800, 800), color=(10, 200, 30)) + b"\0" * 4096)
    assert resp.status_code == 413
    assert resp.json()["error"] == "image_too_large"
    assert fake_gemini.calls == []


def test_prepare_image_errors():
    cfg = load_gemini_config()
    from services.gemini.images import prepare_image

    with pytest.raises(InvalidImageError):
        prepare_image(b"", cfg)
    with pytest.raises(ImageTooLargeError):
        prepare_image(b"x" * (cfg.max_upload_bytes + 1), cfg)


# --------------------------------------------------------------------------
# 6. invalid Gemini responses + safety blocks
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        make_response("this is not json"),
        make_response(json.dumps({**DEFAULT_DIAGNOSIS, "summary": None})),
        make_response(
            json.dumps({**DEFAULT_DIAGNOSIS, "diagnosis": {**DEFAULT_DIAGNOSIS["diagnosis"], "confidence": 87}})
        ),
        make_response('{"image_quality": "good"', finish_reason="MAX_TOKENS"),
        make_response(None),
    ],
    ids=["not_json", "missing_field", "confidence_out_of_range", "truncated", "empty"],
)
def test_invalid_gemini_response_is_a_502_not_a_made_up_result(client, fake_gemini, response):
    before = len(client.get("/analytics/history?limit=500").json())
    fake_gemini.script.append(response)
    resp = _predict(client)
    assert resp.status_code == 502
    assert resp.json()["error"] == "gemini_invalid_response"
    assert len(fake_gemini.calls) == 1  # not retried
    # Nothing was recorded as a scan.
    assert len(client.get("/analytics/history?limit=500").json()) == before


@pytest.mark.parametrize(
    "response",
    [make_response(None, block_reason="SAFETY"), make_response("{}", finish_reason="SAFETY")],
    ids=["prompt_blocked", "candidate_blocked"],
)
def test_safety_block_is_reported(client, fake_gemini, response):
    fake_gemini.script.append(response)
    resp = _predict(client)
    assert resp.status_code == 422
    assert resp.json()["error"] == "gemini_safety_blocked"


def test_invalid_reasoning_response_on_chat(client, fake_gemini):
    fake_gemini.script.append(make_response('{"answer": "only this"}'))
    resp = client.post("/chat", json={"user_question": "hi"})
    assert resp.status_code == 502
    assert resp.json()["error"] == "gemini_invalid_response"


def test_parse_strips_code_fences():
    text = "```json\n" + json.dumps(DEFAULT_DIAGNOSIS) + "\n```"
    assert gclient.parse_json_model(text, GeminiDiagnosis).summary
    with pytest.raises(GeminiInvalidResponse):
        gclient.parse_json_model("[]", GeminiDiagnosis)


# --------------------------------------------------------------------------
# 7. quota / rate limits, 8. network failures, auth — retry policy
# --------------------------------------------------------------------------


def _daily_quota_error():
    return _api_error(
        429,
        "You exceeded your current quota, please check your plan and billing details.",
        "RESOURCE_EXHAUSTED",
        details=[{"violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}],
    )


def test_quota_exhaustion_is_not_retried_without_a_fallback_model(client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "none")
    fake_gemini.script.append(_daily_quota_error())
    resp = _predict(client)
    assert resp.status_code == 429
    assert resp.json()["error"] == "gemini_quota_exceeded"
    assert len(fake_gemini.calls) == 1


def test_daily_quota_on_one_model_switches_to_the_fallback_model(client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
    fake_gemini.script.append(_daily_quota_error())
    resp = _predict(client)
    assert resp.status_code == 200, resp.text
    assert [c["model"] for c in fake_gemini.calls] == ["gemini-3.5-flash", "gemini-3.5-flash-lite"]
    assert resp.json()["metadata"]["gemini"]["model"] == "gemini-3.5-flash-lite"


def test_quota_exhausted_on_both_models_is_reported(client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite")
    fake_gemini.script.extend([_daily_quota_error(), _daily_quota_error()])
    resp = _predict(client)
    assert resp.status_code == 429
    assert resp.json()["error"] == "gemini_quota_exceeded"
    assert len(fake_gemini.calls) == 2


def test_rate_limit_is_retried_with_backoff_then_succeeds(client, fake_gemini):
    fake_gemini.script.append(_api_error(429, "Resource has been exhausted (e.g. check quota).", "RESOURCE_EXHAUSTED"))
    resp = _predict(client)
    assert resp.status_code == 200, resp.text
    assert len(fake_gemini.calls) == 2
    assert resp.json()["metadata"]["gemini"]["call"]["attempts"] == 2


def test_persistent_rate_limit_stops_after_max_retries(client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "2")
    fake_gemini.script.extend([_api_error(429, "Too many requests", "RESOURCE_EXHAUSTED")] * 5)
    resp = _predict(client)
    assert resp.status_code == 429
    assert resp.json()["error"] == "gemini_rate_limited"
    assert len(fake_gemini.calls) == 3


@pytest.mark.parametrize(
    "exc, status, code",
    [
        (httpx.ConnectError("connection refused"), 503, "gemini_network_error"),
        (httpx.ReadTimeout("read timed out"), 504, "gemini_timeout"),
        (_api_error(503, "The model is overloaded.", "UNAVAILABLE"), 503, "gemini_unavailable"),
    ],
    ids=["network", "timeout", "server_overloaded"],
)
def test_transient_failures_are_retried_then_reported(client, fake_gemini, monkeypatch, exc, status, code):
    monkeypatch.setenv("GEMINI_MAX_RETRIES", "2")
    fake_gemini.script.extend([exc] * 3)
    resp = _predict(client)
    assert resp.status_code == status
    assert resp.json()["error"] == code
    assert len(fake_gemini.calls) == 3


def test_backoff_grows_exponentially(monkeypatch):
    monkeypatch.setenv("GEMINI_BACKOFF_BASE_SECONDS", "1")
    monkeypatch.setenv("GEMINI_BACKOFF_MAX_SECONDS", "100")
    c = gclient.GeminiClient(load_gemini_config(), sdk_client=object())
    monkeypatch.setattr(gclient.random, "random", lambda: 1.0)
    assert [c._backoff(i) for i in range(4)] == [1.0, 2.0, 4.0, 8.0]


@pytest.mark.parametrize(
    "exc",
    [
        _api_error(400, "API key not valid. Please pass a valid API key.", "INVALID_ARGUMENT"),
        _api_error(403, "Permission denied", "PERMISSION_DENIED"),
    ],
    ids=["invalid_key", "forbidden"],
)
def test_auth_errors_are_not_retried_and_hide_the_key(client, fake_gemini, caplog, exc):
    caplog.set_level(logging.DEBUG)
    fake_gemini.script.append(exc)
    resp = _predict(client)
    assert resp.status_code == 502
    assert resp.json()["error"] == "gemini_auth_failed"
    assert len(fake_gemini.calls) == 1
    assert FAKE_GEMINI_KEY not in resp.text and FAKE_GEMINI_KEY not in caplog.text


def test_failed_scan_persists_nothing_and_can_be_retried(client, fake_gemini, tmp_path):
    fake_gemini.script.append(httpx.ConnectError("down"))
    fake_gemini.script.append(httpx.ConnectError("down"))
    fake_gemini.script.append(httpx.ConnectError("down"))
    image = _jpeg()
    assert _predict(client, image).status_code == 503
    assert list((tmp_path / "uploads").iterdir()) == []
    retry = _predict(client, image)
    assert retry.status_code == 200
    assert len(list((tmp_path / "uploads").iterdir())) == 1


def test_report_with_image_surfaces_gemini_errors(client, fake_gemini):
    fake_gemini.script.append(_api_error(400, "API key not valid.", "INVALID_ARGUMENT"))
    resp = client.post("/report", files={"file": ("x.jpg", _jpeg(), "image/jpeg")})
    assert resp.status_code == 502
    assert resp.json()["error"] == "gemini_auth_failed"


def test_secret_in_exception_text_is_not_logged(client, fake_gemini, caplog):
    caplog.set_level(logging.DEBUG)
    fake_gemini.script.append(RuntimeError(f"weird failure with key={FAKE_GEMINI_KEY}"))
    resp = _predict(client)
    assert resp.status_code == 502
    assert FAKE_GEMINI_KEY not in resp.text and FAKE_GEMINI_KEY not in caplog.text


# --------------------------------------------------------------------------
# 10. frontend compatibility
# --------------------------------------------------------------------------


def test_predict_response_has_every_field_the_frontend_reads(client):
    client.post("/sensor", json={"device_id": "esp32_001", "air_temperature": 22, "air_humidity": 55})
    body = _predict(client).json()
    # app.js showPredictResult / home.js / assistant.js
    for key in ("disease", "confidence", "stress_hint", "class_name", "disease_type", "accepted",
                "model_name", "plant", "health", "metadata", "zone_id", "user_id",
                "gemini_verdict", "gemini_agrees", "gemini_reasoning"):
        assert key in body
    for key in ("common_name", "scientific_name", "family", "genus", "confidence"):
        assert key in body["plant"]
    for key in ("plant_health", "disease_risk", "survival_chance", "recommendation"):
        assert key in body["health"]
    for key in ("raw_disease_label", "image_url", "zone_id", "device_id", "scan_source", "sensor_snapshot"):
        assert key in body["metadata"]


def test_chat_accepts_the_frontends_legacy_payload(client):
    """Exactly what app.js sent before this migration (incl. default sensor numbers)."""
    payload = {
        "vision": {"disease": "Powdery Mildew", "confidence": 0.8, "stress_hint": "unknown",
                   "class_name": "powdery_mildew", "disease_type": "powdery_mildew", "accepted": True,
                   "plant": {"common_name": "Cucumber"}, "health": None},
        "sensors": {"soil_moisture": 50, "temperature": 25, "humidity": 60, "species": "Cucumber"},
        "user_question": "What now?",
    }
    body = client.post("/chat", json=payload).json()
    assert body["source"] == "gemini" and body["reply"] and body["recommendation"]
    assert "breakdown" in body and "survival_probability" in body


def test_health_endpoints_report_yolo_disabled_and_gemini_live(client):
    services = client.get("/health/services").json()
    assert services["gemini_status"] == "live"
    assert services["yolo_status"] == "disabled"
    assert services["plantnet_status"] == "disabled"
    models = client.get("/models/health").json()
    assert models["ai_provider"] == "google_gemini"
    assert models["vision_loaded"] is False and models["llama_loaded"] is False
    assert models["local_models"]["yolo"] == "disabled"


# --------------------------------------------------------------------------
# 11. no local model is loaded, 12. no local fallback runs
# --------------------------------------------------------------------------


@pytest.fixture
def tripwires(monkeypatch):
    """Make every legacy local-AI entry point explode if anything touches it."""

    import models.disease_model as dm
    import models.llama_model as lm
    import models.plant_id_model as pm
    import services.model_manager as mm

    def boom(*_a, **_k):
        raise AssertionError("legacy local AI path was used")

    monkeypatch.setattr(dm.SpeciesAwareVisionPredictor, "__init__", boom)
    monkeypatch.setattr(dm.YoloVisionPredictor, "__init__", boom)
    monkeypatch.setattr(dm.StubVisionPredictor, "predict", boom)
    monkeypatch.setattr(dm.MultiProviderConsensusPredictor, "predict", boom)
    monkeypatch.setattr(dm, "get_vision_predictor", boom)
    monkeypatch.setattr(lm, "fallback_narrative", boom)
    monkeypatch.setattr(lm, "get_llama_client", boom)
    monkeypatch.setattr(lm.LlamaClient, "generate_chat", boom)
    monkeypatch.setattr(pm, "get_plant_id_predictor", boom)
    monkeypatch.setattr(pm.StubPlantIdPredictor, "predict", boom)
    monkeypatch.setattr(pm.PlantNetPredictor, "predict", boom)
    monkeypatch.setattr(mm.ModelManager, "instance", classmethod(lambda cls: boom()))
    monkeypatch.delitem(sys.modules, "ultralytics", raising=False)


def test_no_local_model_runs_on_any_ai_route(client, tripwires):
    image = _jpeg()
    assert _predict(client, image).status_code == 200
    assert client.post(
        "/analyze",
        files={"file": ("x.jpg", image, "image/jpeg")},
        data={"soil_moisture": "50", "temperature": "25", "humidity": "60"},
    ).status_code == 200
    assert client.post("/report", files={"file": ("x.jpg", image, "image/jpeg")}).status_code == 200
    assert client.post("/chat", json={"user_question": "hi"}).status_code == 200
    assert client.get("/models/health").status_code == 200
    assert "ultralytics" not in sys.modules


@pytest.mark.parametrize("route", ["predict", "chat", "analyze"])
def test_gemini_failure_never_falls_back_to_local_ai(client, fake_gemini, tripwires, route):
    fake_gemini.script.extend([httpx.ConnectError("down")] * 10)
    if route == "predict":
        resp = _predict(client)
    elif route == "chat":
        resp = client.post("/chat", json={"user_question": "hi"})
    else:
        resp = client.post(
            "/analyze",
            files={"file": ("x.jpg", _jpeg(), "image/jpeg")},
            data={"soil_moisture": "50", "temperature": "25", "humidity": "60"},
        )
    assert resp.status_code == 503
    assert resp.json()["error"] == "gemini_network_error"
    assert "rule-based" not in resp.text and "offline" not in resp.text.lower()


def test_production_modules_do_not_import_legacy_local_ai():
    import ast
    from pathlib import Path

    backend = Path(__file__).resolve().parent.parent
    legacy = {"models", "models.disease_model", "models.llama_model", "models.plant_id_model",
              "services.model_manager", "services.gemini_second_opinion", "ultralytics"}
    offenders = []
    for path in list((backend / "routes").glob("*.py")) + list((backend / "services").rglob("*.py")) + [backend / "main.py"]:
        if path.name in ("model_manager.py", "gemini_second_opinion.py"):
            continue  # the disabled modules themselves
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            offenders += [f"{path.name}: {n}" for n in names if n in legacy or n.startswith("models.")]
    assert offenders == []


def test_direct_diagnosis_call_uses_injected_client(fake_gemini):
    outcome = diagnose_plant_image(_jpeg())
    assert outcome.diagnosis.diagnosis.primary_condition == "Powdery Mildew"
    assert outcome.cached is False and outcome.call["operation"] == "diagnosis"
