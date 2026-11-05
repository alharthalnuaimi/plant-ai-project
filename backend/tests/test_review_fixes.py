"""Regression tests for reviewed bug fixes. All providers are mocked; keys are fake."""

from __future__ import annotations

import base64
import io
import logging
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
import requests
from PIL import Image

from services.providers.multi_provider import (
    PROVIDER_REGISTRY,
    GeminiAgent,
    KimiAgent,
    RoboflowAgent,
    _parse_structured_response,
)

FAKE_KEY = "TEST_KEY_123"


def _agent(result):
    agent = MagicMock()
    agent.annotate.return_value = result
    return agent


def _consensus(*results):
    registry = type(PROVIDER_REGISTRY)()
    agents = [_agent(r) for r in results]
    with patch.object(type(registry), "active_providers", new_callable=PropertyMock, return_value=agents):
        return registry.run_n_agent_consensus(b"img")


def _vote(label, status):
    return {"provider": "p", "class_label": label, "confidence": 0.9, "bbox": None, "reasoning": "", "status": status}


# --- upload filename -------------------------------------------------------

@pytest.mark.parametrize(
    "filename",
    ["a/../../SENTINEL.txt", "a\\..\\..\\SENTINEL.txt", "../SENTINEL.txt", "..\\SENTINEL.txt"],
)
def test_predict_filename_cannot_escape_upload_dir(fastapi_client, jpeg_bytes, tmp_path, monkeypatch, filename):
    from routes import predict

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    sentinel = tmp_path / "SENTINEL.txt"
    sentinel.write_text("original")
    monkeypatch.setattr(predict, "UPLOAD_DIR", uploads)
    monkeypatch.setenv("STORAGE_BACKEND", "local")

    resp = fastapi_client.post(
        "/predict",
        files={"file": (filename, jpeg_bytes, "image/jpeg")},
        data={"species_id": "cucumber", "identify": "false"},
    )

    assert resp.status_code == 200
    assert sentinel.read_text() == "original"
    saved = list(uploads.iterdir())
    assert len(saved) == 1 and saved[0].suffix == ".jpg"


# --- only decoded images are stored ------------------------------------------

@pytest.mark.parametrize(
    "payload",
    [b"<script>alert(1)</script>" + b"x" * 400, b'<svg xmlns="http://www.w3.org/2000/svg"></svg>' + b" " * 400],
    ids=["html", "svg"],
)
def test_non_image_upload_is_rejected_and_not_saved(fastapi_client, tmp_path, monkeypatch, payload):
    from routes import predict

    monkeypatch.setattr(predict, "UPLOAD_DIR", tmp_path)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    resp = fastapi_client.post("/predict", files={"file": ("evil.html", payload, "image/png")})
    assert resp.status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_truncated_image_is_rejected(fastapi_client, jpeg_bytes, tmp_path, monkeypatch):
    from routes import predict

    monkeypatch.setattr(predict, "UPLOAD_DIR", tmp_path)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    resp = fastapi_client.post("/predict", files={"file": ("x.jpg", jpeg_bytes[:len(jpeg_bytes) // 2], "image/jpeg")})
    assert resp.status_code == 400
    assert list(tmp_path.iterdir()) == []


def test_extension_comes_from_the_decoded_format(fastapi_client, tmp_path, monkeypatch):
    from routes import predict

    monkeypatch.setattr(predict, "UPLOAD_DIR", tmp_path)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    resp = fastapi_client.post(
        "/predict",
        files={"file": ("evil.html", _png() + b"\0" * 512, "image/jpeg")},
        data={"species_id": "cucumber", "identify": "false"},
    )
    assert resp.status_code == 200
    assert [p.suffix for p in tmp_path.iterdir()] == [".png"]


def test_supabase_upload_gets_the_decoded_type(fastapi_client, monkeypatch):
    from routes import predict
    from services.storage import StorageUploadResult

    calls = {}

    async def fake_upload(*, file_bytes, filename, content_type):
        calls.update(filename=filename, content_type=content_type)
        return StorageUploadResult(ok=False, error="mocked")

    monkeypatch.setattr(predict.storage, "is_enabled", lambda: True)
    monkeypatch.setattr(predict.storage, "upload_scan_image", fake_upload)
    resp = fastapi_client.post(
        "/predict",
        files={"file": ("evil.html", _png() + b"\0" * 512, "image/jpeg")},
        data={"species_id": "cucumber", "identify": "false"},
    )
    assert resp.status_code == 200
    assert calls == {"filename": "scan.png", "content_type": "image/png"}


def test_uploads_mount_serves_images_only(tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from main import ImageStaticFiles

    (tmp_path / "old.html").write_text("<script>alert(1)</script>")
    (tmp_path / "old.svg").write_text("<svg></svg>")
    (tmp_path / "old_leaf.JPG").write_bytes(b"jpeg")
    app = FastAPI()
    app.mount("/uploads", ImageStaticFiles(directory=str(tmp_path)))
    client = TestClient(app)
    assert client.get("/uploads/old.html").status_code == 404
    assert client.get("/uploads/old.svg").status_code == 404
    image = client.get("/uploads/old_leaf.JPG")
    assert image.status_code == 200
    assert image.headers["x-content-type-options"] == "nosniff"


# --- label matching ---------------------------------------------------------

@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Unhealthy", "diseased"),
        ("Not healthy", "diseased"),
        ("Abnormal", "diseased"),
        ("no healthy tissue left", "diseased"),
        ("Smoke damage", "unknown"),
        ("Okra mosaic", "unknown"),
        ("something else", "unknown"),
        ("", "unknown"),
        ("Healthy", "healthy"),
        ("Healthy Money Plant", "healthy"),
        ("OK", "healthy"),
        ("normal", "healthy"),
        ("none", "healthy"),
        ("no disease", "healthy"),
        ("No visible signs of disease", "healthy"),
        ("not diseased", "healthy"),
        ("no rust", "healthy"),
        ("not rust but powdery mildew", "powdery_mildew"),
        ("healthy leaf with rust spots", "leaf_spot"),
        ("Powdery Mildew", "powdery_mildew"),
        ("cucumber_downy_mildew", "downy_mildew"),
        ("Bacterial Wilt", "bacterial_wilt"),
        ("Leaf Spot", "leaf_spot"),
        ("rust", "leaf_spot"),
        ("blight", "bacterial_wilt"),
        ("late blight", "diseased"),
        ("root rot", "diseased"),
        ("Diseased", "diseased"),
    ],
)
def test_label_matching(label, expected):
    from services.disease_taxonomy import classify_disease

    assert classify_disease(label)["class_name"] == expected


@pytest.mark.parametrize("label", ["Unhealthy", "Not healthy", "Abnormal"])
def test_scan_status_does_not_pass_unhealthy_labels(label):
    from services.analytics_store import _is_healthy_disease

    assert _is_healthy_disease(label) is False


# --- Gemini argument -------------------------------------------------------

def test_gemini_client_accepts_system_instruction():
    from models.llama_model import GeminiClient

    with patch("models.llama_model.genai") as genai:
        genai.Client.return_value.models.generate_content.return_value = MagicMock(text="ok")
        out = GeminiClient(api_key=FAKE_KEY, model="m").generate_chat(
            messages=[{"role": "user", "content": "hi"}],
            system_instruction="be brief",
        )
    kwargs = genai.Client.return_value.models.generate_content.call_args.kwargs
    assert out == "ok"
    assert kwargs["config"].system_instruction == "be brief"


def test_gemini_agent_reaches_client_and_votes(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    with patch("models.llama_model.genai") as genai:
        genai.Client.return_value.models.generate_content.return_value = MagicMock(
            text='{"label": "Rust", "confidence": 0.8, "bbox": null, "reasoning": "r"}'
        )
        result = GeminiAgent().annotate(b"img", context_label="")
    assert result["status"] == "success"
    assert result["class_label"] == "Rust"


# --- the image reaches the model --------------------------------------------

def _png():
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), (1, 2, 3)).save(buf, format="PNG")
    return buf.getvalue()


def test_gemini_consensus_vote_receives_the_image(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    image = _png()
    with patch("models.llama_model.genai") as genai:
        genai.Client.return_value.models.generate_content.return_value = MagicMock(text='{"label": "Rust", "confidence": 0.8}')
        GeminiAgent().annotate(image)
    part, text = genai.Client.return_value.models.generate_content.call_args.kwargs["contents"]
    assert part.inline_data.data == image
    assert part.inline_data.mime_type == "image/png"
    assert "plant" in text.lower()


def test_gemini_second_opinion_receives_the_image(monkeypatch):
    from services.gemini_second_opinion import evaluate_gemini_second_opinion

    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    image = _png()
    with patch("models.llama_model.genai") as genai:
        genai.Client.return_value.models.generate_content.return_value = MagicMock(text="I agree. Rust.")
        evaluate_gemini_second_opinion(image, "Rust", 0.9)
    part, _ = genai.Client.return_value.models.generate_content.call_args.kwargs["contents"]
    assert part.inline_data.data == image


def test_gemini_text_only_chat_is_unchanged():
    from models.llama_model import GeminiClient

    with patch("models.llama_model.genai") as genai:
        genai.Client.return_value.models.generate_content.return_value = MagicMock(text="ok")
        GeminiClient(api_key=FAKE_KEY, model="m").generate_chat(messages=[{"role": "user", "content": "hi"}])
    assert genai.Client.return_value.models.generate_content.call_args.kwargs["contents"] == "hi"


def test_kimi_vote_receives_the_image(monkeypatch):
    monkeypatch.setenv("KIMI_API_KEY", FAKE_KEY)
    image = _png()
    with patch("openai.OpenAI") as openai:
        create = openai.return_value.chat.completions.create
        create.return_value.choices[0].message.content = '{"label": "Rust", "confidence": 0.8}'
        result = KimiAgent().annotate(image)
    content = create.call_args.kwargs["messages"][0]["content"]
    assert content[0]["image_url"]["url"] == "data:image/png;base64," + base64.b64encode(image).decode()
    assert "vision" in create.call_args.kwargs["model"] or create.call_args.kwargs["model"].startswith("kimi-")
    assert result["status"] == "success"


def test_provider_connection_test_sends_a_real_image(fastapi_client, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    with patch("models.llama_model.genai") as genai:
        genai.Client.return_value.models.generate_content.return_value = MagicMock(text='{"label": "Rust", "confidence": 0.8}')
        resp = fastapi_client.post("/admin/providers/test", json={"provider_name": "GEMINI_API_KEY"})
    part, _ = genai.Client.return_value.models.generate_content.call_args.kwargs["contents"]
    assert resp.status_code == 200
    assert Image.open(io.BytesIO(part.inline_data.data)).format == "JPEG"


# --- API keys never appear ---------------------------------------------------

def _roboflow_401(url, params=None, **_):
    resp = requests.Response()
    resp.status_code = 401
    resp.reason = "Unauthorized"
    resp.url = requests.Request("POST", url, params=params).prepare().url
    return resp


def _roboflow_conn_error(url, params=None, **_):
    prepared = requests.Request("POST", url, params=params).prepare().url
    raise requests.ConnectionError(f"Max retries exceeded with url: {prepared}")


@pytest.mark.parametrize("failure", [_roboflow_401, _roboflow_conn_error], ids=["401", "connection_error"])
def test_roboflow_key_never_appears(fastapi_client, jpeg_bytes, monkeypatch, caplog, failure):
    from routes import predict as predict_route

    monkeypatch.setenv("ROBOFLOW_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ROBOFLOW_MODEL_ENDPOINT", "fake-model/1")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    caplog.set_level(logging.DEBUG)
    stored = []
    real_record = predict_route.analytics_store.record_scan
    monkeypatch.setattr(
        predict_route.analytics_store, "record_scan",
        lambda result: (stored.append(result.model_dump_json()), real_record(result))[1],
    )
    with patch("requests.post", side_effect=failure):
        test_resp = fastapi_client.post("/admin/providers/test", json={"provider_name": "ROBOFLOW_API_KEY"})
        scan_resp = fastapi_client.post(
            "/predict",
            files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")},
            data={"species_id": "cucumber", "identify": "false"},
        )
    assert test_resp.status_code == 200 and scan_resp.status_code == 200
    assert test_resp.json()["test_result"]["status"] == "error"  # the path under test really ran
    assert scan_resp.json()["metadata"]["provider_results"][0]["status"] == "error"
    assert len(stored) == 1  # what gets persisted as metadata_json
    history = fastapi_client.get("/scans/history").text
    for text in (test_resp.text, scan_resp.text, stored[0], history, caplog.text):
        assert FAKE_KEY not in text


def test_roboflow_error_still_reports_type_and_status(monkeypatch):
    monkeypatch.setenv("ROBOFLOW_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ROBOFLOW_MODEL_ENDPOINT", "fake-model/1")
    with patch("requests.post", side_effect=_roboflow_401):
        result = RoboflowAgent().annotate(b"img")
    assert "HTTPError" in result["reasoning"] and "401" in result["reasoning"]


@pytest.mark.parametrize("agent_cls", [GeminiAgent, KimiAgent], ids=["gemini", "kimi"])
def test_other_providers_do_not_echo_exception_text(monkeypatch, caplog, agent_cls):
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("KIMI_API_KEY", FAKE_KEY)
    secret_error = RuntimeError(f"bad key {FAKE_KEY}")
    with patch("models.llama_model.genai") as genai, patch("openai.OpenAI", side_effect=secret_error):
        genai.Client.side_effect = secret_error
        result = agent_cls().annotate(b"img")
    assert FAKE_KEY not in str(result) and FAKE_KEY not in caplog.text


def test_second_opinion_does_not_echo_exception_text(monkeypatch, caplog):
    from services.gemini_second_opinion import evaluate_gemini_second_opinion

    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    with patch("models.llama_model.genai") as genai:
        genai.Client.side_effect = RuntimeError(f"bad key {FAKE_KEY}")
        result = evaluate_gemini_second_opinion(b"img", "Rust", 0.9)
    assert FAKE_KEY not in str(result) and FAKE_KEY not in caplog.text


def test_plantnet_key_is_not_logged(jpeg_bytes, monkeypatch, caplog):
    import httpx

    import main  # noqa: F401 - configures logging the way the running app does
    from models.plant_id_model import PlantNetPredictor

    monkeypatch.setenv("PLANTNET_API_KEY", FAKE_KEY)
    caplog.set_level(logging.INFO)
    real_client = httpx.Client
    seen = []

    def transport(req):
        seen.append(str(req.url))
        return httpx.Response(200, json={"results": []})

    with patch("httpx.Client", lambda **k: real_client(transport=httpx.MockTransport(transport), **k)):
        PlantNetPredictor().predict(jpeg_bytes)
    assert FAKE_KEY in seen[0]  # the request really carried the key, so the log check means something
    assert logging.getLogger("httpx").level == logging.WARNING
    assert FAKE_KEY not in caplog.text


def test_plantnet_failure_is_not_logged_with_url(jpeg_bytes, monkeypatch, caplog):
    import httpx

    from models.plant_id_model import PlantNetPredictor

    monkeypatch.setenv("PLANTNET_API_KEY", FAKE_KEY)
    with patch("httpx.Client", side_effect=httpx.ConnectError(f"failed for api-key={FAKE_KEY}")):
        PlantNetPredictor().predict(jpeg_bytes)
    assert FAKE_KEY not in caplog.text


# --- what counts as a vote -------------------------------------------------

@pytest.mark.parametrize("status", ["stubbed", "error", "no_result"])
def test_non_answers_never_vote(status):
    result = _consensus(_vote("Healthy", status))
    assert result["consensus_label"] == "Unknown"
    assert result["consensus_rate"] == 0.0


def test_non_answers_cannot_outvote_a_real_answer():
    result = _consensus(_vote("Healthy", "stubbed"), _vote("Healthy", "error"), _vote("Rust", "success"))
    assert result["consensus_label"] == "Rust"
    assert result["consensus_rate"] == 1.0


@pytest.mark.parametrize("raw", ["not json at all", '{"confidence": 0.9}', '{"label": "", "confidence": 0.9}'])
def test_answer_without_a_label_is_not_a_vote(raw):
    assert _parse_structured_response(raw, "", "p")["status"] == "no_result"


def test_failing_gemini_is_not_reported_as_healthy(fastapi_client, jpeg_bytes, monkeypatch):
    """The original bug: a Gemini failure came back as Healthy at 100% confidence."""
    monkeypatch.setenv("GEMINI_API_KEY", FAKE_KEY)
    with patch("models.llama_model.genai") as genai:
        genai.Client.return_value.models.generate_content.side_effect = RuntimeError("boom")
        resp = fastapi_client.post(
            "/predict",
            files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")},
            data={"species_id": "cucumber", "identify": "false"},
        )
    body = resp.json()
    assert resp.status_code == 200
    assert body["disease"] == "Unknown"
    assert body["confidence"] == 0.0
    assert body["accepted"] is False
    assert FAKE_KEY not in resp.text
