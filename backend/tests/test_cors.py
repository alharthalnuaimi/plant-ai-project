"""
Phase 4 — CORS allowlist parser tests.

These cover ``core.cors.parse_cors_origins`` / ``resolved_cors_origins``
without booting the FastAPI app, so they cost ~0ms and have zero
external dependencies (no DB, no FastAPI TestClient).

The parser MUST:
* Preserve the legacy ``["*"]`` default whenever the env var is missing,
  empty, whitespace-only, or literally ``"*"``.
* Split comma-separated values, strip whitespace, drop empties, and
  de-dupe while preserving insertion order.
* Fall back to ``["*"]`` if the value parses to nothing usable.
"""

from __future__ import annotations

import pytest

from core.cors import parse_cors_origins, resolved_cors_origins


class TestParseCorsOrigins:
    def test_none_returns_wildcard(self):
        assert parse_cors_origins(None) == ["*"]

    def test_empty_string_returns_wildcard(self):
        assert parse_cors_origins("") == ["*"]

    def test_whitespace_only_returns_wildcard(self):
        assert parse_cors_origins("   \t\n  ") == ["*"]

    def test_literal_star_returns_wildcard(self):
        assert parse_cors_origins("*") == ["*"]
        assert parse_cors_origins("  *  ") == ["*"]

    def test_single_origin(self):
        assert parse_cors_origins("http://localhost:3000") == [
            "http://localhost:3000"
        ]

    def test_multiple_origins_preserve_order(self):
        value = "http://localhost:3000,https://plantvision.vercel.app"
        assert parse_cors_origins(value) == [
            "http://localhost:3000",
            "https://plantvision.vercel.app",
        ]

    def test_whitespace_is_stripped_around_each_entry(self):
        value = "  http://a.example , https://b.example "
        assert parse_cors_origins(value) == [
            "http://a.example",
            "https://b.example",
        ]

    def test_empty_entries_dropped(self):
        value = "http://a.example,,https://b.example,"
        assert parse_cors_origins(value) == [
            "http://a.example",
            "https://b.example",
        ]

    def test_duplicates_deduplicated(self):
        value = "http://a.example,http://a.example,https://b.example"
        assert parse_cors_origins(value) == [
            "http://a.example",
            "https://b.example",
        ]

    def test_only_commas_returns_wildcard(self):
        # No usable origin survives the split → fall back to wide-open
        # rather than disabling CORS entirely.
        assert parse_cors_origins(",,,") == ["*"]


class TestResolvedCorsOrigins:
    def test_uses_injected_env(self):
        env = {"CORS_ALLOWED_ORIGINS": "https://example.com"}
        assert resolved_cors_origins(env) == ["https://example.com"]

    def test_missing_env_falls_back_to_wildcard(self):
        assert resolved_cors_origins({}) == ["*"]

    def test_empty_env_value_falls_back_to_wildcard(self):
        env = {"CORS_ALLOWED_ORIGINS": ""}
        assert resolved_cors_origins(env) == ["*"]


def test_cors_helper_is_importable_from_main():
    """Catch regressions where main.py stops calling resolved_cors_origins()."""
    import main  # noqa: F401

    assert hasattr(main, "_CORS_ORIGINS")
    assert isinstance(main._CORS_ORIGINS, list)
    assert main._CORS_ORIGINS  # never empty
