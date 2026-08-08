"""Tests for multi-provider structured output parsing & consensus (Task 9).

Tests the _parse_structured_response helper and verifies that:
  (a) Inactive providers return stub response without calling the network
  (b) A structured JSON response parses into the correct shape
  (c) No hardcoded confidence values exist in provider responses
"""

import json
from unittest.mock import patch, MagicMock

from services.providers.multi_provider import (
    _parse_structured_response,
    GeminiAgent,
    ClaudeAgent,
    GPTAgent,
    KimiAgent,
    RoboflowAgent,
    PROVIDER_REGISTRY,
)


class TestParseStructuredResponse:
    def test_valid_json_response(self):
        raw = json.dumps({
            "label": "Powdery Mildew",
            "confidence": 0.82,
            "bbox": [0.3, 0.4, 0.5, 0.6],
            "reasoning": "White patches visible on leaf surface.",
        })
        result = _parse_structured_response(raw, "Healthy", "TestProvider")
        assert result["class_label"] == "Powdery Mildew"
        assert result["confidence"] == 0.82
        assert result["bbox"] == [0.3, 0.4, 0.5, 0.6]
        assert result["status"] == "success"

    def test_json_in_markdown_code_fence(self):
        raw = '```json\n{"label": "Healthy", "confidence": 0.95, "bbox": null, "reasoning": "No issues."}\n```'
        result = _parse_structured_response(raw, "Bacterial Wilt", "TestProvider")
        assert result["class_label"] == "Healthy"
        assert result["confidence"] == 0.95
        assert result["bbox"] is None

    def test_confidence_clamped_to_0_1(self):
        raw = json.dumps({"label": "Test", "confidence": 1.5, "bbox": None, "reasoning": ""})
        result = _parse_structured_response(raw, "", "TestProvider")
        assert result["confidence"] == 1.0

        raw2 = json.dumps({"label": "Test", "confidence": -0.3, "bbox": None, "reasoning": ""})
        result2 = _parse_structured_response(raw2, "", "TestProvider")
        assert result2["confidence"] == 0.0

    def test_invalid_json_returns_zero_confidence(self):
        raw = "This is not valid JSON at all, just text about plants"
        result = _parse_structured_response(raw, "Healthy", "TestProvider")
        assert result["confidence"] == 0.0
        assert "[Unstructured response]" in result["reasoning"]

    def test_partial_json_still_parses(self):
        raw = 'Some preamble text {"label": "Rust", "confidence": 0.7, "bbox": null, "reasoning": "spots"} trailing'
        result = _parse_structured_response(raw, "", "TestProvider")
        assert result["class_label"] == "Rust"
        assert result["confidence"] == 0.7


class TestInactiveProviders:
    """Inactive providers must return stub response without network calls."""

    def test_gemini_stub(self):
        agent = GeminiAgent()
        with patch.dict("os.environ", {}, clear=True):
            result = agent.annotate(b"test_bytes", context_label="test")
            assert result["status"] == "stubbed"
            assert result["confidence"] == 0.0

    def test_claude_stub(self):
        agent = ClaudeAgent()
        with patch.dict("os.environ", {}, clear=True):
            result = agent.annotate(b"test_bytes", context_label="test")
            assert result["status"] == "stubbed"
            assert result["confidence"] == 0.0

    def test_gpt_stub(self):
        agent = GPTAgent()
        with patch.dict("os.environ", {}, clear=True):
            result = agent.annotate(b"test_bytes", context_label="test")
            assert result["status"] == "stubbed"
            assert result["confidence"] == 0.0

    def test_kimi_stub(self):
        agent = KimiAgent()
        with patch.dict("os.environ", {}, clear=True):
            result = agent.annotate(b"test_bytes", context_label="test")
            assert result["status"] == "stubbed"
            assert result["confidence"] == 0.0

    def test_roboflow_stub_without_endpoint(self):
        """Roboflow should be stubbed if ROBOFLOW_MODEL_ENDPOINT is missing."""
        agent = RoboflowAgent()
        with patch.dict("os.environ", {"ROBOFLOW_API_KEY": "test_key"}, clear=True):
            assert not agent.is_active
            result = agent.annotate(b"test_bytes")
            assert result["status"] == "stubbed"
            assert "ROBOFLOW_MODEL_ENDPOINT" in result["reasoning"]


class TestNoHardcodedConfidence:
    """Verify no hardcoded confidence values leak into provider responses (Task 5 acceptance)."""

    def test_no_hardcoded_values_in_source(self):
        """Grep-style check: no 0.85, 0.88, 0.90 confidence constants in provider responses."""
        import inspect
        source = inspect.getsource(GeminiAgent.annotate)
        assert "0.85" not in source

        source = inspect.getsource(ClaudeAgent.annotate)
        assert "0.88" not in source

        source = inspect.getsource(GPTAgent.annotate)
        assert "0.90" not in source


class TestConsensus:
    def test_no_active_providers_returns_empty(self):
        with patch.dict("os.environ", {}, clear=True):
            registry = type(PROVIDER_REGISTRY)()
            result = registry.run_n_agent_consensus(b"test", "Healthy")
            assert result["active_provider_count"] == 0
            assert result["consensus_rate"] == 0.0
