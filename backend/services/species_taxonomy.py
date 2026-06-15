"""
Plant species taxonomy (Phase 3).

Maps a `species_id` slug → display name, scientific name, family, and lightweight
provenance fields used by the unified plant report. Kept here (and not in
`configs/`) because the entries are short and stable; if you add hundreds of
species you should migrate this to ``configs/species.yaml`` and load it via
``services.config_loader``.

This module is intentionally **read-only**: identification models call
``lookup(species_id)`` to enrich their output, and the unified report layer
calls ``family_for(species_id)`` for grouping.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpeciesEntry:
    species_id: str
    common_name: str
    scientific_name: str
    family: str
    aliases: tuple[str, ...] = ()


# Curated catalog. The MVP only ships cucumber + a small set of common
# greenhouse companions so the stub identifier has somewhere reasonable to
# fall back to in the future. The Phase 3 stub locks to "cucumber".
_CATALOG: dict[str, SpeciesEntry] = {
    "cucumber": SpeciesEntry(
        species_id="cucumber",
        common_name="Cucumber",
        scientific_name="Cucumis sativus",
        family="Cucurbitaceae",
        aliases=("cucumis_sativus", "garden_cucumber"),
    ),
    "tomato": SpeciesEntry(
        species_id="tomato",
        common_name="Tomato",
        scientific_name="Solanum lycopersicum",
        family="Solanaceae",
        aliases=("solanum_lycopersicum",),
    ),
    "pepper_bell": SpeciesEntry(
        species_id="pepper_bell",
        common_name="Bell Pepper",
        scientific_name="Capsicum annuum",
        family="Solanaceae",
        aliases=("bell_pepper", "capsicum_annuum"),
    ),
    "lettuce": SpeciesEntry(
        species_id="lettuce",
        common_name="Lettuce",
        scientific_name="Lactuca sativa",
        family="Asteraceae",
        aliases=("lactuca_sativa",),
    ),
    "basil": SpeciesEntry(
        species_id="basil",
        common_name="Basil",
        scientific_name="Ocimum basilicum",
        family="Lamiaceae",
        aliases=("ocimum_basilicum", "sweet_basil"),
    ),
    "strawberry": SpeciesEntry(
        species_id="strawberry",
        common_name="Strawberry",
        scientific_name="Fragaria × ananassa",
        family="Rosaceae",
        aliases=("fragaria_ananassa",),
    ),
}

DEFAULT_SPECIES_ID = "cucumber"


def lookup(species_id: str | None) -> SpeciesEntry:
    """Resolve a species_id (or alias) to a concrete catalog entry.

    Falls back to the cucumber default — used by the stub identifier and by
    the unified report when no species was supplied.
    """

    if not species_id:
        return _CATALOG[DEFAULT_SPECIES_ID]
    key = species_id.strip().lower().replace(" ", "_")
    if key in _CATALOG:
        return _CATALOG[key]
    for entry in _CATALOG.values():
        if key in entry.aliases or key == entry.scientific_name.lower().replace(" ", "_"):
            return entry
    return _CATALOG[DEFAULT_SPECIES_ID]


def family_for(species_id: str | None) -> str:
    return lookup(species_id).family


def all_species() -> list[SpeciesEntry]:
    return list(_CATALOG.values())
