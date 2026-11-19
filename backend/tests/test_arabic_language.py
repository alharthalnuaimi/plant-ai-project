"""English/Arabic language support.

* ``language`` is optional everywhere; without it (or with ``en``) every
  request, prompt, schema and response is exactly what it was before.
* ``language=ar`` asks Gemini for an additional Arabic block next to the
  canonical English diagnosis (which is what gets persisted), and asks the
  reasoning call to answer in Arabic.
* ``?lang=ar`` on read endpoints translates the backend's rule-based
  English text in the response only; nothing stored changes.
"""

from __future__ import annotations

import io
import re

import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image

import routes.predict as predict_route
from config.paths import REPO_ROOT
from main import app
from services import localization
from services.disease_taxonomy import CLASS_CATALOG
from services.gemini.prompts import DIAGNOSIS_SYSTEM, REASONING_SYSTEM

ARABIC = re.compile(r"[؀-ۿ]")

AR_LOCALIZED = {
    "condition": "البياض الدقيقي",
    "summary": "تظهر على أوراق الخيار بقع بيضاء مسحوقية تتوافق مع البياض الدقيقي.",
    "recommended_action": "أزل الأوراق الأشد إصابة وحسّن التهوية.",
    "observations": ["بقع بيضاء مسحوقية على السطح العلوي للأوراق"],
    "uncertainties": ["السطح السفلي للأوراق غير ظاهر."],
    "image_quality_notes": None,
    "plant_common_name": "الخيار",
    "alternative_diagnoses": ["البياض الزغبي — السطح السفلي غير ظاهر"],
}


def _jpeg(color=(40, 110, 60)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), color).save(buf, format="JPEG", quality=85)
    return buf.getvalue()


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
        "/predict", files={"file": ("leaf.jpg", image or _jpeg(), "image/jpeg")}, data=data
    )


def _diagnosis_calls(fake):
    return [
        c for c in fake.calls
        if getattr(getattr(c["config"], "response_schema", None), "__name__", "").startswith("GeminiDiagnosis")
    ]


# --------------------------------------------------------------------------
# /predict
# --------------------------------------------------------------------------


def test_predict_without_language_is_unchanged(client, fake_gemini):
    resp = _predict(client)
    assert resp.status_code == 200, resp.text
    call = _diagnosis_calls(fake_gemini)[0]
    assert call["config"].response_schema.__name__ == "GeminiDiagnosis"
    assert call["config"].system_instruction == DIAGNOSIS_SYSTEM
    meta = resp.json()["metadata"]
    assert "localized" not in meta["gemini_diagnosis"]
    assert "language" not in meta


def test_predict_in_arabic_requests_an_arabic_block_and_keeps_english_canonical(client, fake_gemini):
    fake_gemini.diagnosis["localized"] = AR_LOCALIZED
    resp = _predict(client, language="ar")
    assert resp.status_code == 200, resp.text

    call = _diagnosis_calls(fake_gemini)[0]
    assert call["config"].response_schema.__name__ == "GeminiDiagnosisLocalized"
    assert call["config"].system_instruction.startswith(DIAGNOSIS_SYSTEM)
    assert "Arabic" in call["config"].system_instruction

    body = resp.json()
    assert body["disease"] == "Powdery Mildew"  # canonical, persisted, used by analytics
    meta = body["metadata"]
    assert meta["raw_disease_label"] == "Powdery Mildew"
    assert meta["language"] == "ar"
    assert meta["gemini_diagnosis"]["summary"].startswith("Cucumber")
    assert meta["gemini_diagnosis"]["localized"]["condition"] == "البياض الدقيقي"


def test_unknown_language_falls_back_to_english(client, fake_gemini):
    resp = _predict(client, language="xx")
    assert resp.status_code == 200, resp.text
    assert _diagnosis_calls(fake_gemini)[0]["config"].system_instruction == DIAGNOSIS_SYSTEM


def test_diagnosis_cache_is_separated_by_language(client, fake_gemini):
    image = _jpeg((10, 120, 30))
    fake_gemini.diagnosis["localized"] = AR_LOCALIZED
    _predict(client, image=image)
    _predict(client, image=image, language="ar")
    _predict(client, image=image, language="ar")
    _predict(client, image=image)
    assert len(_diagnosis_calls(fake_gemini)) == 2


def test_arabic_retake_guidance_is_added_next_to_the_english_one(client, fake_gemini):
    fake_gemini.diagnosis.update(image_quality="unusable", image_quality_notes="Too dark.")
    fake_gemini.diagnosis["localized"] = dict(AR_LOCALIZED, image_quality_notes="الصورة مظلمة جداً.")
    meta = _predict(client, language="ar").json()["metadata"]
    assert "Retake" in meta["guidance"]
    assert ARABIC.search(meta["guidance_localized"])


def test_consistency_rules_also_clear_the_arabic_condition(client, fake_gemini):
    fake_gemini.diagnosis.update(image_quality="unusable")
    fake_gemini.diagnosis["localized"] = AR_LOCALIZED
    dx = _predict(client, language="ar").json()["metadata"]["gemini_diagnosis"]
    assert dx["diagnosis"]["primary_condition"] is None
    assert dx["localized"]["condition"] is None


def test_predict_response_rule_text_is_arabic_with_lang_query(client, fake_gemini):
    fake_gemini.diagnosis["localized"] = AR_LOCALIZED
    resp = client.post(
        "/predict?lang=ar",
        files={"file": ("leaf.jpg", _jpeg((5, 90, 20)), "image/jpeg")},
        data={"language": "ar"},
    )
    body = resp.json()
    assert body["disease"] == "Powdery Mildew"
    assert ARABIC.search(body["health"]["recommendation"])


# --------------------------------------------------------------------------
# /chat
# --------------------------------------------------------------------------


def _reasoning_calls(fake):
    return fake.calls_for("GeminiReasoning")


def test_chat_without_language_is_unchanged(client, fake_gemini):
    assert client.post("/chat", json={"user_question": "How is my plant?"}).status_code == 200
    assert _reasoning_calls(fake_gemini)[0]["config"].system_instruction == REASONING_SYSTEM


def test_chat_in_arabic_asks_gemini_to_answer_in_arabic(client, fake_gemini):
    resp = client.post("/chat", json={"user_question": "كيف حال نبتتي؟", "language": "ar"})
    assert resp.status_code == 200, resp.text
    instruction = _reasoning_calls(fake_gemini)[0]["config"].system_instruction
    assert instruction.startswith(REASONING_SYSTEM)
    assert "Arabic" in instruction


# --------------------------------------------------------------------------
# Rule-based text translation
# --------------------------------------------------------------------------


def test_translate_text_leaves_english_and_unknown_strings_alone():
    s = "Maintain current irrigation and monitor weekly."
    assert localization.translate_text(s, "en") == s
    assert localization.translate_text("zone_alpha", "ar") == "zone_alpha"
    assert ARABIC.search(localization.translate_text(s, "ar"))


def test_translate_text_handles_templated_sentences():
    out = localization.translate_text("Plant looks healthy (91/100). Continue monitoring; no immediate action required.", "ar")
    assert "91/100" in out and ARABIC.search(out)
    out = localization.translate_text("Watering schedule: Every 2-3 days", "ar")
    assert ARABIC.search(out) and "Every" not in out


def _string_leaves(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from _string_leaves(v)
    elif isinstance(node, list):
        for v in node:
            yield from _string_leaves(v)


def test_every_care_template_string_has_an_arabic_copy():
    data = yaml.safe_load((REPO_ROOT / "configs" / "care_templates.yaml").read_text(encoding="utf-8"))
    missing = [
        s for s in set(_string_leaves(data))
        if ARABIC.search(s) is None
        and re.search(r"[A-Za-z]{3,}", s)  # skip NPK ratios like "10-10-10"
        and not ARABIC.search(localization.translate_text(s, "ar"))
    ]
    assert missing == []


def test_every_disease_catalog_text_has_an_arabic_copy():
    for entry in CLASS_CATALOG.values():
        for key in ("display", "recommendation"):
            assert ARABIC.search(localization.translate_text(entry[key], "ar")), entry[key]


def test_localize_payload_never_touches_identifier_or_enum_fields():
    payload = {
        "disease": "Powdery Mildew",
        "status": "Healthy",
        "disease_risk": "Low",
        "zone_id": "zone_alpha",
        "recommendation": "Maintain current irrigation and monitor weekly.",
        "items": [{"label": "Humidity low", "tone": "warn"}],
    }
    out = localization.localize_payload(payload, "ar")
    assert out["disease"] == "Powdery Mildew"
    assert out["status"] == "Healthy"
    assert out["disease_risk"] == "Low"
    assert out["zone_id"] == "zone_alpha"
    assert ARABIC.search(out["recommendation"])
    assert ARABIC.search(out["items"][0]["label"])
    assert out["items"][0]["tone"] == "warn"


def test_report_json_is_arabic_with_lang_query_and_english_without(client):
    body = {"plant_id": "cucumber_001"}
    en = client.post("/report", json=body)
    ar = client.post("/report?lang=ar", json=body)
    assert en.status_code == ar.status_code == 200
    assert not ARABIC.search(en.text)
    assert ARABIC.search(ar.text)
    assert en.json().keys() == ar.json().keys()


def test_sensor_routes_are_never_rewritten(client, monkeypatch):
    # The localizer must never run for sensor routes.
    calls = []
    monkeypatch.setattr(localization, "localize_payload", lambda *a, **k: calls.append(a) or a[0])
    en = client.get("/sensor/latest")
    ar = client.get("/sensor/latest?lang=ar")
    assert en.status_code == ar.status_code
    assert calls == []
    # Same body apart from the live reading age, which changes between calls.
    drop_age = lambda body: {k: v for k, v in body.items() if k != "age_seconds"}
    assert drop_age(en.json()) == drop_age(ar.json())
    assert not ARABIC.search(ar.text)


def test_plant_health_route_is_arabic_with_lang_query(client):
    en = client.get("/health/plant")
    ar = client.get("/health/plant?lang=ar")
    assert en.status_code == ar.status_code == 200
    rec_en = en.json().get("recommendation")
    if rec_en:
        assert ARABIC.search(ar.json()["recommendation"])


def test_report_summary_translates_the_plant_name():
    out = localization.translate_text(
        "cucumber: Unknown suspected. Plant health 78/100, survival chance 72/100.", "ar"
    )
    assert "cucumber" not in out and "الخيار" in out


# --------------------------------------------------------------------------
# Audit fixes
# --------------------------------------------------------------------------


def _ar_scan(client, fake, image=None, **loc_overrides):
    fake.diagnosis["localized"] = dict(AR_LOCALIZED, **loc_overrides)
    resp = client.post(
        "/predict", files={"file": ("l.jpg", image or _jpeg((70, 140, 50)), "image/jpeg")}, data={"language": "ar"}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_scan_lists_expose_the_stored_arabic_text(client, fake_gemini):
    _ar_scan(client, fake_gemini)
    item = client.get("/scans/history?limit=1").json()["scans"][0]
    assert item["disease"] == "Powdery Mildew"  # canonical stays English
    assert item["disease_localized"] == "البياض الدقيقي"
    assert ARABIC.search(item["recommendation_localized"])
    profile = client.get("/scans/plant/cucumber_001").json()
    assert profile["latest_scan"]["disease_localized"] == "البياض الدقيقي"


def test_english_scans_have_no_arabic_fields(client, fake_gemini):
    _predict(client, image=_jpeg((90, 30, 30)))
    item = client.get("/scans/history?limit=1").json()["scans"][0]
    assert item["disease_localized"] is None
    assert item["recommendation_localized"] is None


def test_plant_health_uses_arabic_gemini_advice_only_in_arabic(client, fake_gemini):
    _ar_scan(client, fake_gemini, image=_jpeg((15, 99, 44)))
    en = client.get("/health/plant").json()["recommendation"]
    ar = client.get("/health/plant?lang=ar").json()["recommendation"]
    assert not ARABIC.search(en)
    assert "أزل الأوراق" in ar


def test_report_uses_arabic_gemini_advice_in_arabic(client, fake_gemini):
    _ar_scan(client, fake_gemini, image=_jpeg((22, 77, 33)))
    body = {"plant_id": "cucumber_001"}
    assert "أزل الأوراق" in client.post("/report?lang=ar", json=body).json()["health"]["recommendation"]
    assert not ARABIC.search(client.post("/report", json=body).json()["health"]["recommendation"])


def test_partial_arabic_block_is_accepted(client, fake_gemini):
    fake_gemini.diagnosis["localized"] = {"summary": "ملخص فقط"}
    resp = _predict(client, image=_jpeg((1, 2, 3)), language="ar")
    assert resp.status_code == 200, resp.text
    loc = resp.json()["metadata"]["gemini_diagnosis"]["localized"]
    assert loc["summary"] == "ملخص فقط" and loc["observations"] == [] and loc["condition"] is None


def test_missing_arabic_block_still_scans(client, fake_gemini):
    fake_gemini.diagnosis.pop("localized", None)
    resp = _predict(client, image=_jpeg((4, 5, 6)), language="ar")
    assert resp.status_code == 200, resp.text
    assert resp.json()["metadata"]["gemini_diagnosis"].get("localized") is None


def test_arabic_cache_key_carries_its_own_prompt_version():
    from services.gemini import diagnosis as dg
    from services.gemini.prompts import ARABIC_PROMPT_VERSION

    assert dg._cache_key("h", "m", None) == "h|m|gemini-v3|"
    assert dg._cache_key("h", "m", None, "ar").endswith(f"|ar|{ARABIC_PROMPT_VERSION}")


def test_report_with_image_respects_language(client, fake_gemini):
    fake_gemini.diagnosis["localized"] = AR_LOCALIZED
    resp = client.post(
        "/report?lang=ar",
        files={"file": ("l.jpg", _jpeg((33, 66, 99)), "image/jpeg")},
        data={"language": "ar"},
    )
    assert resp.status_code == 200, resp.text
    assert _diagnosis_calls(fake_gemini)[0]["config"].response_schema.__name__ == "GeminiDiagnosisLocalized"
    assert "أزل الأوراق" in resp.json()["health"]["recommendation"]


def test_analyze_respects_language(client, fake_gemini):
    fake_gemini.diagnosis["localized"] = AR_LOCALIZED
    resp = client.post(
        "/analyze",
        files={"file": ("l.jpg", _jpeg((44, 88, 11)), "image/jpeg")},
        data={"soil_moisture": 40, "temperature": 24, "humidity": 60, "language": "ar"},
    )
    assert resp.status_code == 200, resp.text
    assert _diagnosis_calls(fake_gemini)[0]["config"].response_schema.__name__ == "GeminiDiagnosisLocalized"
    assert "Arabic" in _reasoning_calls(fake_gemini)[0]["config"].system_instruction


def test_analyze_without_language_is_unchanged(client, fake_gemini):
    resp = client.post(
        "/analyze",
        files={"file": ("l.jpg", _jpeg((45, 89, 12)), "image/jpeg")},
        data={"soil_moisture": 40, "temperature": 24, "humidity": 60},
    )
    assert resp.status_code == 200, resp.text
    assert _diagnosis_calls(fake_gemini)[0]["config"].system_instruction == DIAGNOSIS_SYSTEM
    assert _reasoning_calls(fake_gemini)[0]["config"].system_instruction == REASONING_SYSTEM


def test_every_gemini_error_message_has_an_arabic_copy():
    from services.gemini import errors

    for cls in vars(errors).values():
        msg = getattr(cls, "default_message", None)
        if isinstance(msg, str):
            assert ARABIC.search(localization.translate_text(msg, "ar")), msg
    assert ARABIC.search(localization.translate_text("Image is larger than the 8 MB upload limit.", "ar"))


def test_chat_error_message_is_arabic_with_lang_query(client, fake_gemini, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    from services.gemini.client import set_gemini_client

    set_gemini_client(None)
    resp = client.post("/chat?lang=ar", json={"user_question": "مرحبا", "language": "ar"})
    assert resp.status_code == 503
    assert ARABIC.search(resp.text)


def test_arabic_counts_use_correct_plural_forms():
    t = lambda s: localization.translate_text(s, "ar")
    one = t("cucumber: 1 critical environmental issue(s). Plant health 50/100, survival chance 44/100.")
    assert "مشكلة بيئية حرجة واحدة" in one
    three = t("cucumber: 3 environmental warning(s). Plant health 50/100, survival chance 44/100.")
    assert "3 تحذيرات بيئية" in three
    two = t("cucumber: 1 critical environmental issue(s) and 2 additional warning(s). Plant health 50/100, survival chance 44/100.")
    assert "تحذيران إضافيان" in two


def test_analytics_history_exposes_the_arabic_condition(client, fake_gemini):
    _ar_scan(client, fake_gemini, image=_jpeg((61, 62, 63)))
    item = client.get("/analytics/history?limit=1").json()[0]
    assert item["disease"] == "Powdery Mildew"
    assert item["disease_localized"] == "البياض الدقيقي"
