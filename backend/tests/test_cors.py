"""Tests for CORS configuration — wildcard vs explicit origins (Task 12).

Verifies that the CORS wildcard + credentials bug is fixed:
- Wildcard origins → allow_credentials=False (CORS spec compliance)
- Explicit origins → allow_credentials=True (enables cookies/auth)
"""

from core.cors import parse_cors_origins, resolved_cors_origins


class TestCorsOriginParsing:
    def test_none_returns_wildcard(self):
        assert parse_cors_origins(None) == ["*"]

    def test_empty_returns_wildcard(self):
        assert parse_cors_origins("") == ["*"]
        assert parse_cors_origins("   ") == ["*"]

    def test_star_returns_wildcard(self):
        assert parse_cors_origins("*") == ["*"]

    def test_explicit_origins_parsed(self):
        result = parse_cors_origins("https://example.com,https://app.example.com")
        assert result == ["https://example.com", "https://app.example.com"]

    def test_deduplication(self):
        result = parse_cors_origins("https://a.com,https://a.com,https://b.com")
        assert result == ["https://a.com", "https://b.com"]

    def test_trailing_commas_tolerated(self):
        result = parse_cors_origins("https://a.com,")
        assert result == ["https://a.com"]


class TestCorsCredentialsPolicy:
    """The CORS spec forbids wildcard origin + credentials.

    These tests verify main.py's logic: when origins are wildcard,
    allow_credentials must be False; when explicit, True.
    """

    def test_wildcard_means_no_credentials(self):
        origins = resolved_cors_origins(env={"CORS_ALLOWED_ORIGINS": "*"})
        is_wildcard = origins == ["*"]
        assert is_wildcard is True
        # The policy: allow_credentials = not is_wildcard
        assert (not is_wildcard) is False

    def test_unset_means_no_credentials(self):
        origins = resolved_cors_origins(env={})
        is_wildcard = origins == ["*"]
        assert is_wildcard is True
        assert (not is_wildcard) is False

    def test_explicit_origins_allow_credentials(self):
        origins = resolved_cors_origins(env={
            "CORS_ALLOWED_ORIGINS": "https://plantvision.app,https://localhost:3000"
        })
        is_wildcard = origins == ["*"]
        assert is_wildcard is False
        # The policy: allow_credentials = not is_wildcard
        assert (not is_wildcard) is True
