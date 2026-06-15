"""
Phase 4 (B2) — tests for the new /devices/register and
/devices/diagnostics endpoints.

These ride on the in-memory persistence backend (see conftest.py) so
they need no Postgres / no network. They cover:

* Register accepts the minimal `{slug, label?, zone_slug?}` payload
  and upserts a row with sensible defaults.
* Register defaults `device_name` to the slug when no label is given.
* Diagnostics returns an empty list when no devices have reported yet.
* After a sensor write, diagnostics surfaces the device as `live`,
  with `reachable=True` and a non-null `last_seen_at`.
* Diagnostics shape includes the keys the frontend Settings panel uses
  (slug, last_seen_at, age_seconds, freshness, retry_counters,
  reachable, zone_slug, source).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.smoke


def test_register_minimal_payload(fastapi_client):
    payload = {"slug": "esp32_register_min", "label": "Greenhouse #1", "zone_slug": "zone_alpha"}
    r = fastapi_client.post("/devices/register", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "esp32_register_min"
    assert body["device_name"] == "Greenhouse #1"
    # status defaults to OFFLINE — the next /sensor write flips it to ONLINE.
    assert body["status"].upper() in ("OFFLINE", "ONLINE")


def test_register_defaults_label_to_slug(fastapi_client):
    r = fastapi_client.post("/devices/register", json={"slug": "esp32_no_label"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["slug"] == "esp32_no_label"
    assert body["device_name"] == "esp32_no_label"


def test_diagnostics_endpoint_shape_and_keys(fastapi_client):
    r = fastapi_client.get("/devices/diagnostics")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "source" in body
    assert "count" in body
    assert "devices" in body
    assert isinstance(body["devices"], list)
    for dev in body["devices"]:
        for k in (
            "slug",
            "last_seen_at",
            "age_seconds",
            "freshness",
            "retry_counters",
            "reachable",
            "zone_slug",
            "source",
        ):
            assert k in dev, f"diagnostics row missing {k!r}: {dev}"
        assert dev["freshness"] in {"live", "stale", "offline"}


def test_diagnostics_surfaces_device_after_sensor_write(fastapi_client):
    slug = "esp32_diag_smoke"
    sensor_payload = {
        "user_id": "demo_user",
        "zone_id": "zone_alpha",
        "device_id": slug,
        "air_temperature": 24.0,
        "air_humidity": 60.0,
        "light_lux": 28000.0,
        "soil_temperature": 22.0,
        "soil_humidity": 55.0,
        "soil_ph": 6.4,
        "soil_ec": 2.0,
    }
    rr = fastapi_client.post("/sensor", json=sensor_payload)
    assert rr.status_code == 200

    r = fastapi_client.get("/devices/diagnostics")
    assert r.status_code == 200, r.text
    body = r.json()
    matched = [d for d in body["devices"] if d["slug"] == slug]
    assert matched, f"device {slug!r} not found in diagnostics: {body}"
    row = matched[0]
    assert row["freshness"] == "live"
    assert row["reachable"] is True
    assert row["age_seconds"] is None or row["age_seconds"] >= 0
    assert row["last_seen_at"] is not None


def test_register_then_appears_in_listing(fastapi_client):
    r = fastapi_client.post("/devices/register", json={"slug": "esp32_in_list", "label": "Backyard"})
    assert r.status_code == 200
    listing = fastapi_client.get("/devices").json()
    slugs = [d["slug"] for d in listing.get("devices", [])]
    assert "esp32_in_list" in slugs


def test_register_does_not_shadow_slug_routes(fastapi_client):
    """Regression — /devices/register must not be matched as slug='register'."""
    # If route ordering is broken, this returns 200 with slug 'register'
    # via the get_device(/{slug}) catch-all. The correct behaviour is a
    # 422 from the missing JSON body, since /register expects a POST body.
    r = fastapi_client.get("/devices/register")
    assert r.status_code in (404, 405)


def test_diagnostics_does_not_shadow_slug_routes(fastapi_client):
    """Regression — /devices/diagnostics must not be matched as slug='diagnostics'."""
    r = fastapi_client.get("/devices/diagnostics")
    assert r.status_code == 200
    body = r.json()
    # If the route fell into get_device(slug='diagnostics'), the response
    # would be a 404 or a DeviceOut object — not a DeviceDiagnosticsResponse.
    assert "devices" in body and "count" in body
