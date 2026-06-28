"""Cleanup smoke tests — confirm every public module imports cleanly.

These tests deliberately do *not* exercise behaviour; they only ensure the
package surface stays importable so a stray ``import`` regression in
``main.py``, a route, a schema, or a service breaks here before it breaks
production.

They live in the ``smoke`` marker bucket so they run under
``python -m pytest -m smoke`` alongside the FastAPI TestClient checks.
"""

from __future__ import annotations

import importlib

import pytest

pytestmark = pytest.mark.smoke


_ROUTE_MODULES = (
    "routes.analytics",
    "routes.care",
    "routes.chat",
    "routes.dataset_meta",
    "routes.devices",
    "routes.health_route",
    "routes.predict",
    "routes.report",
    "routes.scans",
    "routes.sensor",
    "routes.survival",
    "routes.zones",
)

_SERVICE_MODULES = (
    "services.analytics_store",
    "services.audit_log",
    "services.care_engine",
    "services.config_loader",
    "services.disease_taxonomy",
    "services.garden_management",
    "services.model_manager",
    "services.orchestrator",
    "services.persistence",
    "services.plant_health",
    "services.prediction",
    "services.report_builder",
    "services.sensor_processing",
    "services.sensor_store",
    "services.species_taxonomy",
    "services.survival",
)

_REPO_MODULES = (
    "repositories.analytics_events_repo",
    "repositories.assistant_repo",
    "repositories.audit_repo",
    "repositories.devices_repo",
    "repositories.scans_repo",
    "repositories.sensor_repo",
    "repositories.zones_repo",
)

_SCHEMA_MODULES = (
    "schemas.analytics",
    "schemas.care",
    "schemas.contracts",
    "schemas.garden",
    "schemas.garden_management",
    "schemas.health",
    "schemas.report",
    "schemas.sensors",
)

_OTHER_MODULES = (
    "main",
    "core.retry",
    "core.errors",
    "core.observability",
    "db.connection",
    "config.settings",
    "models.disease_model",
    "models.llama_model",
    "models.plant_id_model",
)


@pytest.mark.parametrize(
    "module",
    _ROUTE_MODULES + _SERVICE_MODULES + _REPO_MODULES + _SCHEMA_MODULES + _OTHER_MODULES,
)
def test_module_imports(module: str) -> None:
    """Importing the module must not raise — covers typos, circular imports,
    missing dependencies, and broken ``__init__`` re-exports."""

    importlib.import_module(module)


def test_main_app_has_expected_routers() -> None:
    """Confirm every router shipped in Phase 3 is mounted on the FastAPI app."""

    from main import app

    paths = set()
    for route in app.routes:
        if hasattr(route, "path"):
            paths.add(route.path)
        elif hasattr(route, "effective_candidates"):
            for cand in route.effective_candidates():
                if hasattr(cand, "path"):
                    paths.add(cand.path)

    expected = {
        "/health",
        "/health/db",
        "/health/sensor",
        "/health/audit",
        "/health/plant",
        "/predict",
        "/sensor",
        "/sensor/latest",
        "/report",
        "/care",
        "/care/species/{species_id}",
        "/care/{plant_id}",
        "/scans/history",
        "/scans/plant/{plant_id}",
        "/zones",
        "/devices",
    }
    missing = expected - paths
    assert not missing, f"Missing routes on FastAPI app: {sorted(missing)}"


def test_models_package_reexports_plant_id() -> None:
    """``backend.models`` should re-export the plant-ID seam classes."""

    import models  # noqa: WPS433 — package-level import is the point of the test

    for name in (
        "DiseasePrediction",
        "get_vision_predictor",
        "LlamaClient",
        "get_llama_client",
        "PlantIdPrediction",
        "PlantIdPredictor",
        "StubPlantIdPredictor",
        "get_plant_id_predictor",
    ):
        assert hasattr(models, name), f"models.{name} is not exported"


def test_repositories_package_reexports_audit() -> None:
    """``backend.repositories`` should expose every async repo, including audit."""

    import repositories  # noqa: WPS433 — package-level import is the point of the test

    for name in (
        "analytics_events_repo",
        "assistant_repo",
        "audit_repo",
        "devices_repo",
        "scans_repo",
        "sensor_repo",
        "zones_repo",
    ):
        assert hasattr(repositories, name), f"repositories.{name} is not exported"
