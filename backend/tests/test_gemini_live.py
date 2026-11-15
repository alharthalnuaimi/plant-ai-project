"""Optional live integration test against the real Gemini API.

Skipped unless BOTH are set:

    RUN_GEMINI_LIVE_TESTS=1
    GEMINI_API_KEY=<a real key>   (env var or repo-root .env)

Run:  RUN_GEMINI_LIVE_TESTS=1 python -m pytest backend/tests/test_gemini_live.py -q

It makes two small requests (one image diagnosis, one reasoning call) and
only checks that the responses are well-formed — not what the model says.
"""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image, ImageDraw

import config.settings  # noqa: F401 - loads the repo-root .env shim

pytestmark = [pytest.mark.gemini_live, pytest.mark.smoke]


def _enabled() -> bool:
    return os.getenv("RUN_GEMINI_LIVE_TESTS", "").strip() == "1" and bool(
        os.getenv("GEMINI_API_KEY", "").strip()
    )


skip_unless_enabled = pytest.mark.skipif(
    not _enabled(), reason="live Gemini test is opt-in (RUN_GEMINI_LIVE_TESTS=1 + GEMINI_API_KEY)"
)


def _leaf_jpeg() -> bytes:
    img = Image.new("RGB", (512, 512), (235, 235, 225))
    draw = ImageDraw.Draw(img)
    draw.ellipse((96, 140, 416, 372), fill=(46, 125, 50))
    draw.line((110, 256, 400, 256), fill=(27, 94, 32), width=6)
    for x, y in ((180, 210), (260, 300), (330, 230)):
        draw.ellipse((x, y, x + 26, y + 26), fill=(240, 240, 240))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@skip_unless_enabled
def test_live_diagnosis_and_reasoning() -> None:
    from services.gemini import build_reasoning_context, diagnose_plant_image, reason_about_plant
    from services.gemini.schemas import GeminiDiagnosis, GeminiReasoning

    outcome = diagnose_plant_image(_leaf_jpeg())
    assert isinstance(outcome.diagnosis, GeminiDiagnosis)
    assert outcome.call and outcome.call["attempts"] >= 1

    ctx = build_reasoning_context(
        diagnosis=outcome.diagnosis.model_dump(),
        vision_summary=None,
        sensors={"air_temperature": 24.0, "air_humidity": 82.0, "soil_humidity": 55.0},
        survival=None,
        history=None,
        user_question="What should I do first?",
    )
    reasoning = reason_about_plant(ctx)
    assert isinstance(reasoning.reasoning, GeminiReasoning)
    assert reasoning.reply_text()
