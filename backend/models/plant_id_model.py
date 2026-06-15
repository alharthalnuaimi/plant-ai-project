"""
Plant identification — separate from disease detection.

Architecture
============
Two abstract responsibilities:

    Disease detection   →   models.disease_model.VisionPredictor
    Plant identification →  models.plant_id_model.PlantIdPredictor

They are intentionally split so a real species classifier (Pl@ntNet,
torchvision, HuggingFace ViT, etc.) can be plugged in later without
touching the disease pipeline. ``ModelManager.get_plant_id_model()`` is
the single resolution point.

Phase 3 ships only ``StubPlantIdPredictor``: a heuristic that locks to
``cucumber`` for the MVP demo, but emits the full structured response
shape (``species_id``, ``common_name``, ``scientific_name``, ``family``,
``confidence``, ``source``) so frontend + persistence can be wired today.

To plug in a real model later
-----------------------------
1. Create a new class implementing ``PlantIdPredictor.predict``.
2. Register it in ``get_plant_id_predictor()`` based on env / registry.
3. Map its raw labels onto a ``species_id`` known to
   ``services.species_taxonomy._CATALOG`` (or extend the catalog).
4. No change required to /predict, /report, or the schemas.
"""

from __future__ import annotations

import io
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from PIL import Image

from services.species_taxonomy import (
    DEFAULT_SPECIES_ID,
    SpeciesEntry,
    lookup,
)

log = logging.getLogger("plantvision.plant_id")


@dataclass
class PlantIdPrediction:
    species_id: str
    common_name: str
    scientific_name: str
    family: str
    confidence: float       # 0..1
    source: str             # 'stub' | 'yolo' | 'plantnet' | 'plantid' | 'manual' | ...
    raw: dict[str, Any]
    # Phase Final — optional genus parsed from real-classifier responses
    # (e.g. Pl@ntNet returns ``species.genus.scientificNameWithoutAuthor``).
    # Optional with a default so the stub + every existing call site keep
    # working unchanged.
    genus: str | None = None


class PlantIdPredictor(ABC):
    """Abstract plant identification model."""

    @abstractmethod
    def predict(self, image_bytes: bytes) -> PlantIdPrediction:
        ...


# ---------------------------------------------------------------------------
# Stub implementation (Phase 3 default)
# ---------------------------------------------------------------------------


class StubPlantIdPredictor(PlantIdPredictor):
    """Heuristic identifier — ships with the MVP.

    * Validates the image (so a malformed upload still surfaces an error).
    * Emits a low/medium confidence so downstream code treats it as
      provisional rather than authoritative.
    * Locks output to the ``cucumber`` species so the rest of the Phase 3
      pipeline (care recommendations, scientific-name display, plant
      profile aggregation) has a stable identity to test against.

    Future: extend to a real classifier without changing the public ABC
    or any caller — see module docstring.
    """

    def __init__(self, species_id: str = DEFAULT_SPECIES_ID, confidence: float = 0.55):
        self._species_id = species_id
        self._confidence = max(0.0, min(1.0, float(confidence)))

    def predict(self, image_bytes: bytes) -> PlantIdPrediction:
        # Validate image — keeps the stub honest and gives the same
        # error surface as a real classifier on a corrupt upload.
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        w, h = img.size
        if w < 16 or h < 16:
            raise ValueError("Image too small for plant identification")

        entry: SpeciesEntry = lookup(self._species_id)
        return PlantIdPrediction(
            species_id=entry.species_id,
            common_name=entry.common_name,
            scientific_name=entry.scientific_name,
            family=entry.family,
            confidence=self._confidence,
            source="stub",
            raw={
                "model": "stub_plant_id",
                "image_size": [w, h],
                "policy": "default_to_cucumber",
            },
        )


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Pl@ntNet implementation (Phase Final — optional, defaults to stub fallback)
# ---------------------------------------------------------------------------


class PlantNetPredictor(PlantIdPredictor):
    """Pl@ntNet API wrapper that **always** returns a ``PlantIdPrediction``.

    Design rules (graduation-demo safe):

    * If ``PLANTNET_API_KEY`` (preferred) / ``PLANT_ID_API_KEY`` (deprecated)
      is missing/empty at call time we never hit the network — we
      transparently delegate to ``StubPlantIdPredictor`` so the seam stays
      demo-safe in every environment.
    * On any HTTP / network / parse failure we log a warning and fall back to
      the stub. ``predict()`` never raises for transport-level errors. The
      stub still validates the image, so genuinely corrupt uploads still raise
      ``ValueError`` (same contract as the stub).
    * The HTTP call is synchronous (``httpx.Client``) because the
      ``PlantIdPredictor.predict`` seam is synchronous; switching to async
      would force a wider refactor through ``services.prediction`` and the
      /predict route. Synchronous httpx is part of the same `httpx`
      dependency already pinned in ``requirements.txt``.
    """

    API_URL = "https://my-api.plantnet.org/v2/identify/all"

    def __init__(
        self,
        api_key: str | None = None,
        timeout_sec: float = 8.0,
        project: str = "all",
        fallback: PlantIdPredictor | None = None,
    ) -> None:
        if api_key is not None:
            resolved = api_key
        else:
            # Prefer the new name; fall back to the legacy one so existing
            # deployments that already set PLANT_ID_API_KEY don't break.
            resolved = (
                os.getenv("PLANTNET_API_KEY")
                or os.getenv("PLANT_ID_API_KEY")  # deprecated, retained for backward compat
                or ""
            )
        self._api_key = resolved.strip()
        self._timeout = max(1.0, float(timeout_sec))
        self._project = project or "all"
        self._fallback = fallback or StubPlantIdPredictor()

    # -- helpers ------------------------------------------------------------

    def _fallback_predict(self, image_bytes: bytes) -> PlantIdPrediction:
        return self._fallback.predict(image_bytes)

    @staticmethod
    def _resolve_species_id(scientific_name: str | None, family: str | None) -> str:
        """Map a Pl@ntNet scientific name onto our local catalog ID.

        Falls back to ``DEFAULT_SPECIES_ID`` if there is no match — callers
        still receive the real Pl@ntNet ``common_name`` / ``scientific_name``
        / ``family`` for display, but ``species_id`` stays bound to a known
        care plan so the rest of Phase 3 (care engine, plant profile) keeps
        working.
        """

        if scientific_name:
            key = scientific_name.lower().strip().replace(" ", "_")
            entry = lookup(key)
            if entry.species_id != DEFAULT_SPECIES_ID or key in ("cucumis_sativus", "cucumber"):
                return entry.species_id
        return DEFAULT_SPECIES_ID

    # -- main API -----------------------------------------------------------

    def predict(self, image_bytes: bytes) -> PlantIdPrediction:
        # Validate the image up-front (same surface as the stub) so a
        # corrupt upload fails fast before the network call.
        Image.open(io.BytesIO(image_bytes)).convert("RGB")

        if not self._api_key:
            log.info("PlantNetPredictor: no PLANTNET_API_KEY set, returning stub prediction")
            return self._fallback_predict(image_bytes)

        # httpx is in requirements.txt (already used by services/storage.py).
        try:
            import httpx  # local import keeps cold-start cheap when stub is used
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("PlantNetPredictor: httpx unavailable (%s) — falling back to stub", exc)
            return self._fallback_predict(image_bytes)

        params = {"api-key": self._api_key, "include-related-images": "false"}
        files = [("images", ("leaf.jpg", image_bytes, "image/jpeg"))]
        data = {"organs": "leaf"}
        url = f"{self.API_URL.rstrip('/')}".replace("/identify/all", f"/identify/{self._project}")

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, params=params, files=files, data=data)
            if resp.status_code >= 400:
                log.warning("PlantNetPredictor: API returned %s — falling back to stub", resp.status_code)
                return self._fallback_predict(image_bytes)
            payload = resp.json()
        except Exception as exc:  # noqa: BLE001 — never crash /predict
            log.warning("PlantNetPredictor: request failed (%s) — falling back to stub", exc)
            return self._fallback_predict(image_bytes)

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list) or not results:
            log.warning("PlantNetPredictor: empty / malformed response — falling back to stub")
            return self._fallback_predict(image_bytes)

        top = results[0] if isinstance(results[0], dict) else None
        species = (top or {}).get("species") or {}
        scientific_name = (
            species.get("scientificNameWithoutAuthor")
            or species.get("scientificName")
            or ""
        )
        common_names = species.get("commonNames") or []
        common_name = common_names[0] if isinstance(common_names, list) and common_names else (
            scientific_name or "Unknown plant"
        )
        family = ((species.get("family") or {}).get("scientificNameWithoutAuthor")) or ""
        # Pl@ntNet returns a nested ``genus`` block with the same shape as
        # ``family``. Pull the scientific (without-author) form so callers
        # get e.g. "Solanum" rather than "Solanum L.".
        genus_block = species.get("genus") or {}
        genus = (
            genus_block.get("scientificNameWithoutAuthor")
            or genus_block.get("scientificName")
            or ""
        )
        try:
            confidence = float(top.get("score", 0.0)) if top else 0.0
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        species_id = self._resolve_species_id(scientific_name, family)

        return PlantIdPrediction(
            species_id=species_id,
            common_name=str(common_name),
            scientific_name=str(scientific_name or "Unknown"),
            family=str(family or "Unknown"),
            confidence=round(confidence, 4),
            source="plantnet",
            raw={
                "model": "plantnet_v2",
                "project": self._project,
                "result_count": len(results),
            },
            genus=str(genus) if genus else None,
        )


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def get_plant_id_predictor() -> PlantIdPredictor:
    """Resolve the active plant identifier.

    Hook order:
      1. ``PLANT_ID_MODEL=plantnet`` (default) → Pl@ntNet wrapper that falls
         back to the stub on any failure (missing key, network, 4xx/5xx,
         parse). Reads ``PLANTNET_API_KEY`` (preferred) or the legacy
         ``PLANT_ID_API_KEY`` for backward compat.
      2. ``PLANT_ID_MODEL=stub`` → ship-with-MVP heuristic.
      3. Anything else → stub (warning logged).
    """

    backend = (os.getenv("PLANT_ID_MODEL") or "plantnet").strip().lower()
    if backend == "stub":
        return StubPlantIdPredictor()
    if backend == "plantnet":
        return PlantNetPredictor()

    log.warning("Unknown PLANT_ID_MODEL=%s — falling back to stub", backend)
    return StubPlantIdPredictor()
