"""Every API operation: one success and one failure case, on the memory backend, no network.

Tests marked ``known_bug`` describe the correct behaviour for known open bugs.
They are strict xfails, so fixing a bug turns its test red until the marker is removed.
"""

from __future__ import annotations

import io
import re
import zipfile

import pytest
from fastapi.testclient import TestClient

from main import app
from routes import admin_datasets, predict


def known_bug(reason):
    return pytest.mark.xfail(strict=True, reason=f"known bug: {reason}")


@pytest.fixture
def client(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    monkeypatch.setattr(predict, "UPLOAD_DIR", uploads)
    monkeypatch.setattr(admin_datasets, "UPLOADS_ROOT", tmp_path)
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    for key in ("GEMINI_API_KEY", "PLANTNET_API_KEY", "PLANT_ID_API_KEY", "ROBOFLOW_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "KIMI_API_KEY"):
        monkeypatch.setenv(key, "")
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


VISION = {"disease": "Rust", "confidence": 0.8}
SENSORS = {"soil_moisture": 50, "temperature": 25, "humidity": 60}
READING = {"device_id": "esp32_001", "air_temperature": 24, "air_humidity": 60, "soil_ph": 6.5}


def _dataset_zip(jpeg_bytes, meta=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("images/a.jpg", jpeg_bytes)
        z.writestr("labels/a.txt", "0 0.5 0.5 0.5 0.5")
        if meta:
            z.writestr("consensus_meta.json", meta)
    return buf.getvalue()


def _image_form(jpeg_bytes, **data):
    return {"files": {"file": ("x.jpg", jpeg_bytes, "image/jpeg")}, "data": {"species_id": "cucumber", "identify": "false", **data}}


# --- reads: (path, keys the frontend relies on) ---------------------------

READS = [
    ("/health", ["status", "uptime_sec"]),
    ("/health/db", ["persistence_backend", "postgres_reachable"]),
    ("/health/services", ["gemini_status", "plantnet_status", "yolo_status"]),
    ("/health/plant", ["plant_health", "disease_risk", "survival_chance"]),
    ("/health/sensor", ["devices", "status"]),
    ("/health/audit", ["events", "count"]),
    ("/models/health", ["vision_loaded", "vision_version"]),
    ("/models/registry", ["resolved_weights"]),
    ("/dataset/info", ["yolo"]),
    ("/dataset/classes", ["names", "count"]),
    ("/analytics/summary", ["total_scans", "avg_confidence", "scan_outcomes", "top_diseases"]),
    ("/analytics/insights", ["items", "source"]),
    ("/analytics/garden", ["summary", "zones", "devices", "alerts", "activity"]),
    ("/zones", ["zones", "source"]),
    ("/devices", ["devices", "source"]),
    ("/devices/diagnostics", ["devices", "count"]),
    ("/sensor/latest", ["source", "freshness"]),
    ("/scans/history?limit=5", ["scans", "total", "source"]),
    ("/scans/zone-counts", ["counts"]),
    ("/scans/plant/cucumber_001", ["plant_name", "recent_scans", "scan_count"]),
    ("/care", ["species_ids", "count"]),
    ("/care/species/cucumber", ["species_id", "watering"]),
    ("/care/cucumber_001", ["template", "current_stage"]),
    ("/zones/zone_alpha/devices", ["devices"]),
    ("/admin/metrics/inference-summary", ["sample_size"]),
]
LIST_READS = [
    "/analytics/history?limit=5", "/analytics/events?limit=5", "/analytics/zones",
    "/admin/datasets", "/admin/feedback/pending", "/admin/providers", "/admin/training/jobs",
]


@pytest.mark.parametrize(("path", "keys"), READS)
def test_read_returns_expected_keys(client, path, keys):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    assert not set(keys) - set(resp.json())


@pytest.mark.parametrize("path", LIST_READS)
def test_list_read_returns_list(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


# --- writes, success ------------------------------------------------------

def test_predict_success(client, jpeg_bytes):
    resp = client.post("/predict", **_image_form(jpeg_bytes))
    assert resp.status_code == 200, resp.text
    assert not {"disease", "confidence", "accepted", "plant", "health", "metadata"} - set(resp.json())


def test_analyze_success(client, jpeg_bytes):
    resp = client.post("/analyze", files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")}, data={"soil_moisture": "50", "temperature": "25", "humidity": "60"})
    assert resp.status_code == 200, resp.text
    assert not {"vision", "survival", "recommendation"} - set(resp.json())


def test_report_json_and_multipart(client, jpeg_bytes):
    for kwargs in ({"json": {"plant_id": "cucumber_001"}}, {"files": {"file": ("x.jpg", jpeg_bytes, "image/jpeg")}}):
        resp = client.post("/report", **kwargs)
        assert resp.status_code == 200, resp.text
        assert not {"scores", "care_plan", "warnings"} - set(resp.json())


def test_sensor_then_survival_and_chat(client):
    assert client.post("/sensor", json=READING).status_code == 200
    assert client.post("/survival", json={"vision": VISION, "sensors": SENSORS}).status_code == 200
    assert client.post("/survival/from-latest-sensor", json=VISION).status_code == 200
    chat = client.post("/chat", json={"vision": VISION, "sensors": SENSORS, "user_question": "hi"})
    assert chat.status_code == 200, chat.text
    assert "reply" in chat.json()


def test_zone_crud(client):
    assert client.post("/zones", json={"slug": "ep_z", "name": "Z"}).status_code == 200
    updated = client.put("/zones/ep_z", json={"slug": "ep_z", "name": "Z2"})
    assert updated.status_code == 200 and updated.json()["name"] == "Z2"
    assert client.delete("/zones/ep_z").status_code == 200


def test_device_crud(client):
    assert client.post("/devices", json={"slug": "ep_d", "device_name": "D"}).status_code == 200
    assert client.post("/devices/register", json={"slug": "ep_r"}).status_code == 200
    assert client.get("/devices/ep_d").status_code == 200
    assert client.put("/devices/ep_d", json={"slug": "ep_d", "device_name": "D2"}).json()["device_name"] == "D2"
    assert client.delete("/devices/ep_d").status_code == 200
    assert client.get("/devices/ep_d").status_code == 404


def test_training_job_lifecycle(client):
    job = client.post("/admin/training/start", json={"dataset_batch_ids": ["b"], "target": "local"})
    assert job.status_code == 200, job.text
    jid = job.json()["id"]
    assert client.get(f"/admin/training/jobs/{jid}").status_code == 200
    done = client.post(f"/admin/training/jobs/{jid}/complete", json={"metrics_after": {"mAP50": 0.9}, "status": "completed"})
    assert done.status_code == 200 and done.json()["status"] == "completed"


def test_dataset_upload_success(client, jpeg_bytes):
    resp = client.post("/admin/datasets/upload", files={"file": ("d.zip", _dataset_zip(jpeg_bytes), "application/zip")})
    assert resp.status_code == 200, resp.text
    assert not {"upload_id", "status", "report"} - set(resp.json())


def test_provider_test_with_no_key_reports_stubbed(client):
    resp = client.post("/admin/providers/test", json={"provider_name": "GEMINI_API_KEY"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["test_result"]["status"] == "stubbed"


# --- failures -------------------------------------------------------------

@pytest.mark.parametrize(
    ("method", "path", "kwargs", "status"),
    [
        ("GET", "/nope", {}, 404),
        ("PATCH", "/zones", {}, 405),
        ("POST", "/predict", {}, 422),
        ("POST", "/predict", {"files": {"file": ("x.txt", b"hello", "text/plain")}}, 400),
        ("POST", "/predict", {"files": {"file": ("x.jpg", b"", "image/jpeg")}}, 400),
        ("POST", "/analyze", {}, 422),
        ("POST", "/sensor", {"json": {}}, 422),
        ("POST", "/sensor", {"json": {"device_id": "x", "air_temperature": 999}}, 422),
        ("POST", "/survival", {"json": {}}, 422),
        ("POST", "/survival/from-latest-sensor", {"json": {}}, 422),
        ("POST", "/chat", {"json": {}}, 422),
        ("POST", "/zones", {"json": {"slug": "", "name": ""}}, 422),
        ("POST", "/devices", {"json": {}}, 422),
        ("POST", "/devices/register", {"json": {}}, 422),
        ("GET", "/devices/no_such_device", {}, 404),
        ("PUT", "/devices/no_such_device", {"json": {}}, 422),
        ("DELETE", "/devices/no_such_device", {}, 404),
        ("GET", "/scans/no_such_scan", {}, 404),
        ("GET", "/admin/training/jobs/none", {}, 404),
        ("POST", "/admin/training/jobs/none/complete", {"json": {"metrics_after": {}}}, 404),
        ("POST", "/admin/providers/test", {"json": {"provider_name": "none"}}, 404),
        ("POST", "/admin/feedback/none/confirm", {"json": {"confirmed_label": "Rust"}}, 404),
        ("POST", "/admin/datasets/upload", {"files": {"file": ("x.txt", b"x", "text/plain")}}, 400),
        ("POST", "/admin/datasets/upload", {"files": {"file": ("x.zip", b"notzip", "application/zip")}}, 400),
        ("GET", "/analytics/history?limit=-5", {}, 422),
        ("GET", "/analytics/events?limit=abc", {}, 422),
        ("GET", "/scans/history?limit=99999", {}, 422),
    ],
)
def test_bad_request_is_rejected(client, method, path, kwargs, status):
    assert client.request(method, path, **kwargs).status_code == status


def test_every_operation_is_covered_by_this_file():
    """Fails when a route is added without a test here."""
    source = open(__file__, encoding="utf-8").read()
    missing = []
    for path, ops in app.openapi()["paths"].items():
        pattern = re.escape(path).replace(r"\{", "{").replace(r"\}", "}")
        pattern = re.sub(r"{[^}]+}", "[^\"'?]+", pattern)
        if not re.search(f"[\"']{pattern}[\"'?]", source):
            missing += [f"{m.upper()} {path}" for m in ops]
    assert not missing


# --- confirmed bugs -------------------------------------------------------

def test_corrupt_image_on_predict_is_a_client_error(client):
    resp = client.post("/predict", files={"file": ("x.jpg", b"notanimage" * 200, "image/jpeg")})
    assert resp.status_code == 400


def test_corrupt_image_on_report_is_a_client_error(client):
    resp = client.post("/report", files={"file": ("x.jpg", b"notanimage" * 200, "image/jpeg")})
    assert resp.status_code == 400


def test_corrupt_image_analyze(client):
    resp = client.post("/analyze", files={"file": ("x.jpg", b"notanimage" * 200, "image/jpeg")}, data={"soil_moisture": "50", "temperature": "25", "humidity": "60"})
    assert resp.status_code == 400


def test_analyze_out_of_range(client, jpeg_bytes):
    resp = client.post("/analyze", files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")}, data={"soil_moisture": "150", "temperature": "25", "humidity": "60"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"
    assert resp.json()["details"][0]["msg"]


@pytest.mark.parametrize("body", ['{"plant_id": 1}', "[1]"])
def test_report_bad_json_shape(client, body):
    resp = client.post("/report", content=body, headers={"content-type": "application/json"})
    assert resp.status_code == 422
    assert resp.json()["error"] == "validation_error"


def test_sensor_infinity_is_422(client):
    resp = client.post("/sensor", content='{"device_id":"x","air_temperature":1e999}', headers={"content-type": "application/json"})
    assert resp.status_code == 422
    assert set(resp.json()["details"][0]) == {"loc", "msg", "type"}  # input is not echoed back


def test_upload_cannot_store_html(client):
    client.post("/predict", files={"file": ("evil.html", b"<script>alert(1)</script>" + b"x" * 400, "image/png")})
    assert not list(predict.UPLOAD_DIR.glob("*.html"))


@known_bug("a report for a named plant ignores that plant's scans")
def test_report_uses_the_named_plants_scan(client, jpeg_bytes):
    client.post("/predict", **_image_form(jpeg_bytes, plant_id="ep_tomato"))
    assert client.post("/report", json={"plant_id": "ep_tomato"}).json()["disease"] != "Unknown"


@pytest.mark.parametrize("species", ["rose", "money_plant"])
def test_listed_species_is_not_routed_to_cucumber(client, jpeg_bytes, species):
    resp = client.post("/predict", files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")}, data={"species_id": species, "identify": "false"})
    assert resp.json()["plant"]["species_id"] == species
    assert "cucumber" not in resp.json()["model_name"]


def test_unlisted_species_is_unknown_everywhere(client, jpeg_bytes):
    resp = client.post("/predict", files={"file": ("x.jpg", jpeg_bytes, "image/jpeg")}, data={"species_id": "dragonfruit", "identify": "false"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["plant"]["species_id"] == "unknown"
    assert resp.json()["plant"]["confidence"] == 0.0
    assert "cucumber" not in resp.json()["model_name"]
    care = client.get("/care/species/dragonfruit")
    assert care.status_code == 200 and care.json()["species_id"] == "unknown"


@pytest.mark.parametrize("species", ["rose", "money_plant", "dragonfruit"])
def test_care_and_report_work_for_species_without_a_template(client, species):
    assert client.get(f"/care/species/{species}").status_code == 200
    assert client.get(f"/care/plant_1?species_id={species}").status_code == 200
    assert client.post("/report", json={"plant_id": "plant_1", "species_id": species}).status_code == 200


def test_register_keeps_existing_device_data(client):
    client.post("/zones", json={"slug": "ep_keep_z", "name": "Z"})
    client.post("/devices", json={"slug": "ep_keep", "device_name": "Keep", "zone_slug": "ep_keep_z", "ip_address": "10.0.0.5", "status": "ONLINE", "metadata": {"fw": "1"}})
    saved = client.post("/devices/register", json={"slug": "ep_keep"}).json()
    assert saved["device_name"] == "Keep"
    assert saved["zone_slug"] == "ep_keep_z"
    assert saved["ip_address"] == "10.0.0.5"
    assert saved["status"] == "ONLINE"
    assert saved["metadata"] == {"fw": "1", "registered_via": "/devices/register"}


def test_register_applies_fields_the_device_sends(client):
    client.post("/devices", json={"slug": "ep_new_vals", "device_name": "Old", "zone_slug": "z_old"})
    saved = client.post("/devices/register", json={"slug": "ep_new_vals", "label": "New", "zone_slug": "z_new"}).json()
    assert (saved["device_name"], saved["zone_slug"]) == ("New", "z_new")


def test_register_new_device_gets_defaults(client):
    saved = client.post("/devices/register", json={"slug": "ep_brand_new"}).json()
    assert (saved["device_name"], saved["status"], saved["zone_slug"]) == ("ep_brand_new", "OFFLINE", None)


@pytest.mark.parametrize("stored", ['{"fw": "1"}', {"fw": "1"}], ids=["json_string", "dict"])
def test_postgres_row_metadata_is_mapped(stored):
    from services.garden_management import _normalize_row

    assert _normalize_row({"slug": "d", "metadata_json": stored})["metadata"] == {"fw": "1"}


def test_fields_the_frontend_reads_exist(client):
    """A1, A2 and A3: the field names the settings and profile pages now use."""
    client.post("/sensor", json=READING)
    client.post("/admin/training/start", json={"dataset_batch_ids": ["b"], "target": "local"})
    assert "resolved_weights" in client.get("/models/registry").json()
    assert "zone_slug" in client.get("/devices/diagnostics").json()["devices"][0]
    assert "created_at" in client.get("/admin/training/jobs").json()[0]


@pytest.mark.parametrize(
    "meta",
    ['{"class_counts": [1]}', '{"class_counts": {"a": "many"}}', '{"agreed_count": "all"}', "[1]", "not json"],
)
def test_bad_dataset_meta_does_not_break_listing(client, jpeg_bytes, meta):
    upload = client.post("/admin/datasets/upload", files={"file": ("d.zip", _dataset_zip(jpeg_bytes, meta), "application/zip")})
    assert upload.status_code == 200, upload.text
    assert "Not usable" in upload.json()["status"]
    assert upload.json()["report"]["ready_to_train"] is False
    assert client.get("/admin/datasets").status_code == 200


def test_old_bad_folder_does_not_break_listing(client, tmp_path):
    bad = tmp_path / "batch_old"
    bad.mkdir()
    (bad / "consensus_meta.json").write_text('{"class_counts": [1]}')
    resp = client.get("/admin/datasets")
    assert resp.status_code == 200
    assert "Not usable" in next(b for b in resp.json() if b["upload_id"] == "batch_old")["status"]


def test_readiness_crash_cleans_up_and_keeps_listing_working(client, jpeg_bytes, tmp_path, monkeypatch):
    def boom(_):
        raise AttributeError("unexpected")

    monkeypatch.setattr(admin_datasets, "evaluate_dataset_readiness", boom)
    resp = client.post("/admin/datasets/upload", files={"file": ("d.zip", _dataset_zip(jpeg_bytes), "application/zip")})
    assert resp.status_code == 400
    assert [p for p in tmp_path.iterdir() if p.name.startswith("batch_")] == []
    (tmp_path / "batch_other").mkdir()
    assert client.get("/admin/datasets").status_code == 200
