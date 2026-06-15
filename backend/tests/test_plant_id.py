"""Phase 3 — unit tests for the plant identification stub + seam."""

from __future__ import annotations

import pytest

from models.plant_id_model import (
    PlantIdPrediction,
    PlantIdPredictor,
    StubPlantIdPredictor,
    get_plant_id_predictor,
)
from services.species_taxonomy import (
    DEFAULT_SPECIES_ID,
    all_species,
    family_for,
    lookup,
)

pytestmark = pytest.mark.unit


def test_species_taxonomy_default():
    e = lookup(None)
    assert e.species_id == DEFAULT_SPECIES_ID == "cucumber"
    assert e.scientific_name == "Cucumis sativus"
    assert e.family == "Cucurbitaceae"


def test_species_taxonomy_resolves_aliases():
    assert lookup("cucumis_sativus").species_id == "cucumber"
    assert lookup("solanum_lycopersicum").species_id == "tomato"


def test_species_taxonomy_unknown_falls_back():
    assert lookup("dragonfruit").species_id == "cucumber"


def test_family_for_helper():
    assert family_for("tomato") == "Solanaceae"
    assert family_for(None) == "Cucurbitaceae"


def test_all_species_returns_catalog():
    species = all_species()
    ids = {s.species_id for s in species}
    assert {"cucumber", "tomato", "pepper_bell", "lettuce", "basil", "strawberry"} <= ids


def test_stub_predictor_returns_cucumber(jpeg_bytes):
    pred = StubPlantIdPredictor().predict(jpeg_bytes)
    assert isinstance(pred, PlantIdPrediction)
    assert pred.species_id == "cucumber"
    assert pred.scientific_name == "Cucumis sativus"
    assert pred.family == "Cucurbitaceae"
    assert pred.source == "stub"
    assert 0 < pred.confidence <= 1


def test_stub_predictor_rejects_tiny_images():
    """Stub still validates the upload — same error surface as real models."""

    import io

    from PIL import Image

    img = Image.new("RGB", (4, 4), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")

    with pytest.raises(ValueError):
        StubPlantIdPredictor().predict(buf.getvalue())


def test_get_plant_id_predictor_default_is_plantnet(monkeypatch):
    """Phase Final — default backend is now ``plantnet`` (not ``stub``).

    Without ``PLANTNET_API_KEY`` the wrapper transparently falls back to
    the stub at ``predict()`` time, so no network is reached. We only
    assert the resolver picks the wrapper class.
    """

    monkeypatch.delenv("PLANT_ID_MODEL", raising=False)
    from models.plant_id_model import PlantNetPredictor

    p = get_plant_id_predictor()
    assert isinstance(p, PlantIdPredictor)
    assert isinstance(p, PlantNetPredictor)


def test_get_plant_id_predictor_stub_env_returns_stub(monkeypatch):
    monkeypatch.setenv("PLANT_ID_MODEL", "stub")
    p = get_plant_id_predictor()
    assert isinstance(p, StubPlantIdPredictor)


def test_get_plant_id_predictor_unknown_env_falls_back(monkeypatch):
    monkeypatch.setenv("PLANT_ID_MODEL", "definitely-not-a-model")
    p = get_plant_id_predictor()
    assert isinstance(p, StubPlantIdPredictor)


# ---------------------------------------------------------------------------
# Phase Final — PlantNet wrapper tests
#
# Both tests prove the wrapper either returns a PlantIdPrediction with the
# real Pl@ntNet metadata (success path) or transparently falls back to the
# stub on transport failure (failure path). Neither test reaches the network.
# ---------------------------------------------------------------------------


def test_plantnet_predictor_success_path_monkeypatched(jpeg_bytes, monkeypatch):
    """Success path: monkeypatched httpx.Client returns a fake 200 payload."""

    from models.plant_id_model import PlantNetPredictor

    class _FakeResp:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {
                        "score": 0.812,
                        "species": {
                            "scientificNameWithoutAuthor": "Solanum lycopersicum",
                            "commonNames": ["Tomato"],
                            "family": {"scientificNameWithoutAuthor": "Solanaceae"},
                            "genus": {"scientificNameWithoutAuthor": "Solanum"},
                        },
                    }
                ]
            }

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *a, **kw):
            return _FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "Client", _FakeClient)

    predictor = PlantNetPredictor(api_key="fake-test-key")
    pred = predictor.predict(jpeg_bytes)

    assert isinstance(pred, PlantIdPrediction)
    assert pred.source == "plantnet"
    assert pred.scientific_name == "Solanum lycopersicum"
    assert pred.common_name == "Tomato"
    assert pred.family == "Solanaceae"
    assert pred.genus == "Solanum"
    assert pred.species_id == "tomato"  # mapped through the local catalog
    assert 0.0 < pred.confidence <= 1.0


def test_plantnet_predictor_falls_back_to_stub_on_network_error(jpeg_bytes, monkeypatch):
    """Failure path: httpx raises → wrapper must NOT raise; returns stub."""

    from models.plant_id_model import PlantNetPredictor

    class _ExplodingClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def post(self, *a, **kw):
            import httpx

            raise httpx.ConnectError("simulated network failure")

    import httpx

    monkeypatch.setattr(httpx, "Client", _ExplodingClient)

    predictor = PlantNetPredictor(api_key="fake-test-key")
    pred = predictor.predict(jpeg_bytes)  # must not raise

    assert isinstance(pred, PlantIdPrediction)
    assert pred.source == "stub"
    assert pred.species_id == "cucumber"


def test_plantnet_predictor_falls_back_when_no_api_key(jpeg_bytes, monkeypatch):
    """Missing PLANTNET_API_KEY (and legacy PLANT_ID_API_KEY) must not hit the network."""

    from models.plant_id_model import PlantNetPredictor

    monkeypatch.delenv("PLANTNET_API_KEY", raising=False)
    monkeypatch.delenv("PLANT_ID_API_KEY", raising=False)
    predictor = PlantNetPredictor(api_key="")
    pred = predictor.predict(jpeg_bytes)
    assert pred.source == "stub"


def test_plantnet_predictor_reads_new_env_var(jpeg_bytes, monkeypatch):
    """PlantNetPredictor must prefer PLANTNET_API_KEY when both names are set."""

    from models.plant_id_model import PlantNetPredictor

    monkeypatch.setenv("PLANTNET_API_KEY", "preferred-new-key")
    monkeypatch.setenv("PLANT_ID_API_KEY", "legacy-key")
    predictor = PlantNetPredictor()
    assert predictor._api_key == "preferred-new-key"


def test_plantnet_predictor_reads_legacy_env_var_for_backward_compat(jpeg_bytes, monkeypatch):
    """Backward compat: PLANT_ID_API_KEY still works when PLANTNET_API_KEY is unset."""

    from models.plant_id_model import PlantNetPredictor

    monkeypatch.delenv("PLANTNET_API_KEY", raising=False)
    monkeypatch.setenv("PLANT_ID_API_KEY", "legacy-only-key")
    predictor = PlantNetPredictor()
    assert predictor._api_key == "legacy-only-key"


def test_get_plant_id_predictor_plantnet_returns_plantnet(monkeypatch):
    from models.plant_id_model import PlantNetPredictor

    monkeypatch.setenv("PLANT_ID_MODEL", "plantnet")
    p = get_plant_id_predictor()
    assert isinstance(p, PlantNetPredictor)
