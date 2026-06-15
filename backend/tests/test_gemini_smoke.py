"""Phase Final — Gemini smoke test.

Skipped automatically when ``GEMINI_API_KEY`` is unset so CI / contributors
who don't have a key never see it fail. When the key is present we make
one real round-trip through ``GeminiClient.generate_chat`` to confirm the
``google-genai`` SDK + auth + selected model are wired correctly.

The previous file lived at ``backend/models/test_gemini.py`` as a top-level
script that called ``dotenv.load_dotenv()`` and ``print()``-ed the answer.
That added an unmanaged ``python-dotenv`` dependency and was not picked up
by pytest. We now rely on the existing dotenv shim in
``config.settings._load_dotenv_if_present`` (loaded transitively when any
backend module imports settings) and use ``pytest.skip`` for the no-key
case.
"""

from __future__ import annotations

import os

import pytest

# Ensure the in-repo dotenv shim has run before reading GEMINI_API_KEY.
import config.settings  # noqa: F401 — triggers _load_dotenv_if_present()

pytestmark = pytest.mark.smoke


def test_gemini_client_smoke() -> None:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        pytest.skip("GEMINI_API_KEY not set — skipping live Gemini smoke test")

    from models.llama_model import GeminiClient

    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    client = GeminiClient(api_key=api_key, model=model)

    text = client.generate_chat(
        [
            {"role": "system", "content": "Reply with the word PONG only."},
            {"role": "user", "content": "ping"},
        ]
    )

    assert isinstance(text, str)
    assert text.strip(), "GeminiClient returned empty response"
