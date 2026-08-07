"""
Unit tests for Phase 8 multi-provider agent consensus & provider management.
"""

from __future__ import annotations

import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(base_dir))

from fastapi.testclient import TestClient
from main import app
from services.providers.multi_provider import PROVIDER_REGISTRY


def test_multi_provider_registry_lists_all_providers():
    """All 5 providers should be registered."""
    providers = PROVIDER_REGISTRY.list_providers()
    assert len(providers) >= 5
    assert any(p["name"] == "Gemini Vision" for p in providers)
    assert any(p["name"] == "Roboflow Auto Label" for p in providers)
    assert any(p["name"] == "Claude Vision" for p in providers)
    assert any(p["name"] == "GPT-4o Vision" for p in providers)
    assert any(p["name"] == "Kimi Vision" for p in providers)


def test_consensus_only_uses_active_providers():
    """Consensus should only run against providers with API keys set.

    If no API keys are configured (test environment), consensus_rate
    should be 0.0 and active_provider_count should reflect reality,
    not include stubs in the vote.
    """
    res = PROVIDER_REGISTRY.run_n_agent_consensus(
        b"sample_img_bytes", context_label="Healthy Money Plant"
    )
    assert "consensus_label" in res
    assert "consensus_rate" in res
    assert "provider_results" in res
    assert "active_provider_count" in res

    # Active count should match actual providers with keys
    active_count = res["active_provider_count"]
    active_providers = PROVIDER_REGISTRY.active_providers
    assert active_count == len(active_providers)

    # If no providers are active, rate should be 0
    if active_count == 0:
        assert res["consensus_rate"] == 0.0


def test_provider_stub_response_shape():
    """Inactive providers should return stubbed status, not fake success."""
    for provider in PROVIDER_REGISTRY.providers:
        if not provider.is_active:
            result = provider.annotate(b"test_bytes", context_label="test")
            assert result["status"] in ("stubbed", "error")
            assert result["confidence"] == 0.0


def test_admin_providers_endpoints():
    client = TestClient(app)

    # Test GET /admin/providers
    res_list = client.get("/admin/providers")
    assert res_list.status_code == 200
    providers_list = res_list.json()
    assert isinstance(providers_list, list)
    assert len(providers_list) >= 5

    # Each provider should have name, active, and env_var fields
    for p in providers_list:
        assert "name" in p
        assert "active" in p
        assert "env_var" in p

    # Test POST /admin/providers/test
    res_test = client.post("/admin/providers/test", json={"provider_name": "Gemini Vision"})
    assert res_test.status_code == 200
    data_test = res_test.json()
    assert data_test["provider"] == "Gemini Vision"
    assert "test_result" in data_test
