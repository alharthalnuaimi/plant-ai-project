"""Model choice, Gemini 3.x request settings, fallback, deadline, model-not-found handling, real readiness check.

Uses the shared fake SDK from conftest; no network.
"""

from __future__ import annotations

import io

import pytest
from google.genai import errors as genai_errors
from PIL import Image

from services.gemini import client as gclient
from services.gemini.config import DEFAULT_FALLBACK_MODEL, DEFAULT_MODEL, load_gemini_config


def _api_error(code: int, message: str, status: str):
    cls = genai_errors.ClientError if code < 500 else genai_errors.ServerError
    return cls(code, {"error": {"code": code, "message": message, "status": status}})


OVERLOADED = _api_error(503, "This model is currently experiencing high demand.", "UNAVAILABLE")
DEADLINE = _api_error(504, "Deadline expired before operation could complete.", "DEADLINE_EXCEEDED")
GONE = _api_error(404, "This model is no longer available to new users.", "NOT_FOUND")


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (40, 120, 60)).save(buf, format="JPEG")
    return buf.getvalue()


def _scan(client):
    return client.post("/predict", files={"file": ("x.jpg", _jpeg(), "image/jpeg")}, data={"identify": "false"})


def _models(fake):
    return [c["model"] for c in fake.calls]


# --- defaults -----------------------------------------------------------------

def test_defaults(monkeypatch):
    for name in ("GEMINI_MODEL", "GEMINI_FALLBACK_MODEL", "GEMINI_MAX_RETRIES", "GEMINI_DEADLINE_SECONDS", "GEMINI_TIMEOUT_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    cfg = load_gemini_config()
    assert DEFAULT_MODEL == "gemini-3.5-flash" == cfg.diagnosis_model == cfg.reasoning_model
    assert cfg.fallback_model == DEFAULT_FALLBACK_MODEL == "gemini-3.5-flash-lite"
    assert (cfg.max_retries, cfg.deadline_s, cfg.timeout_s) == (1, 30.0, 25.0)


def test_fallback_can_be_turned_off(monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "none")
    assert load_gemini_config().fallback_model == ""


# --- request settings per model generation --------------------------------------

def _build(monkeypatch, model, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    c = gclient.GeminiClient(load_gemini_config(), sdk_client=object())
    return c._build_config(model=model, system_instruction=None, temperature=0.2, response_schema=None, timeout_s=10)


def test_gemini3_uses_default_temperature_and_thinking_level(monkeypatch):
    cfg = _build(monkeypatch, "gemini-3.5-flash", GEMINI_THINKING_LEVEL="low", GEMINI_THINKING_BUDGET="512")
    assert cfg.temperature is None
    assert cfg.thinking_config.thinking_level.name == "LOW"
    assert cfg.thinking_config.thinking_budget is None  # never both
    assert cfg.http_options.timeout == 10_000


def test_gemini2_keeps_temperature_and_budget(monkeypatch):
    cfg = _build(monkeypatch, "gemini-2.5-flash", GEMINI_THINKING_LEVEL="low", GEMINI_THINKING_BUDGET="512")
    assert cfg.temperature == 0.2
    assert cfg.thinking_config.thinking_budget == 512
    assert cfg.thinking_config.thinking_level is None


@pytest.mark.parametrize(
    ("model", "expected"),
    [("gemini-3.5-flash", True), ("models/gemini-3.5-flash-lite", True), ("gemini-10-pro", True),
     ("gemini-2.5-flash", False), ("gemini-1.5-pro", False), ("other-model", False)],
)
def test_generation_detection(model, expected):
    assert gclient._is_gemini3(model) is expected


# --- fallback and retry cap ------------------------------------------------------

@pytest.mark.parametrize("first_error", [OVERLOADED, DEADLINE, GONE], ids=["503", "504", "404"])
def test_retry_uses_the_fallback_model(fastapi_client, fake_gemini, first_error):
    fake_gemini.script.append(first_error)
    resp = _scan(fastapi_client)
    assert resp.status_code == 200, resp.text
    assert _models(fake_gemini) == [DEFAULT_MODEL, DEFAULT_FALLBACK_MODEL]
    assert resp.json()["metadata"]["gemini"]["model"] == DEFAULT_FALLBACK_MODEL
    assert resp.json()["model_version"].startswith(f"{DEFAULT_FALLBACK_MODEL}/")


def test_at_most_one_retry_on_high_demand(fastapi_client, fake_gemini):
    fake_gemini.script.extend([OVERLOADED] * 5)
    resp = _scan(fastapi_client)
    assert resp.status_code == 503
    assert resp.json()["error"] == "gemini_unavailable"
    assert len(fake_gemini.calls) == 2


def test_without_fallback_the_retry_uses_the_same_model(fastapi_client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "none")
    fake_gemini.script.append(OVERLOADED)
    assert _scan(fastapi_client).status_code == 200
    assert _models(fake_gemini) == [DEFAULT_MODEL, DEFAULT_MODEL]


# --- model not found -----------------------------------------------------------

def test_missing_model_is_a_server_error_not_a_bad_request(fastapi_client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "none")
    fake_gemini.script.append(GONE)
    resp = _scan(fastapi_client)
    assert resp.status_code == 503
    assert resp.json()["error"] == "gemini_model_unavailable"
    assert len(fake_gemini.calls) == 1  # no point retrying the same missing model
    assert "GEMINI_MODEL" not in resp.json()["message"]


# --- overall time limit --------------------------------------------------------

class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_no_retry_once_the_deadline_is_close(fake_gemini, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(gclient.time, "perf_counter", clock)
    monkeypatch.setenv("GEMINI_DEADLINE_SECONDS", "30")
    c = gclient.GeminiClient(load_gemini_config(), sleep=lambda s: None)

    def slow_failure(**kwargs):
        clock.now += 28.0  # the first attempt used up most of the 30 s
        raise OVERLOADED

    monkeypatch.setattr(c._sdk.models, "generate_content", slow_failure)
    with pytest.raises(gclient.GeminiUnavailable):
        c.generate_text(operation="t", model=DEFAULT_MODEL, contents=["x"])


def test_each_attempt_fits_inside_the_deadline(fake_gemini, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(gclient.time, "perf_counter", clock)
    c = gclient.GeminiClient(load_gemini_config(), sleep=lambda s: None)
    seen = []

    def record(**kwargs):
        seen.append(kwargs["config"].http_options.timeout)
        clock.now += 12.0
        if len(seen) == 1:
            raise OVERLOADED
        return fake_gemini.generate_content(**kwargs)

    monkeypatch.setattr(c._sdk.models, "generate_content", record)
    c.generate_text(operation="t", model=DEFAULT_MODEL, contents=["x"])
    assert seen[0] == 25_000  # per-attempt timeout
    assert seen[1] <= 18_000  # only what is left of the 30 s


# --- real readiness check ------------------------------------------------------

def test_health_is_not_configured_without_a_key(fastapi_client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")
    assert fastapi_client.get("/health/services").json()["gemini_status"] == "not_configured"


def test_health_probes_the_model_and_caches_the_result(fastapi_client, fake_gemini):
    first = fastapi_client.get("/health/services").json()
    assert first["gemini_status"] == "live" and first["gemini_model_in_use"] == DEFAULT_MODEL
    assert len(fake_gemini.calls) == 1
    fastapi_client.get("/health/services")
    assert len(fake_gemini.calls) == 1  # cached, no second probe


def test_health_reports_a_model_that_cannot_be_used(fastapi_client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "none")
    fake_gemini.script.append(GONE)
    body = fastapi_client.get("/health/services").json()
    assert body["gemini_status"] == "unavailable"
    assert body["gemini_last_error"] == "gemini_model_unavailable"
    assert body["gemini_key_present"] is True


def test_real_scans_update_health_without_a_probe(fastapi_client, fake_gemini, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "none")
    fake_gemini.script.append(GONE)
    assert _scan(fastapi_client).status_code == 503
    assert fastapi_client.get("/health/services").json()["gemini_status"] == "unavailable"
    assert len(fake_gemini.calls) == 1  # the scan's own call, no extra probe
    assert _scan(fastapi_client).status_code == 200
    assert fastapi_client.get("/health/services").json()["gemini_status"] == "live"


def test_health_never_shows_the_key(fastapi_client):
    from tests.conftest import FAKE_GEMINI_KEY

    assert FAKE_GEMINI_KEY not in fastapi_client.get("/health/services").text
