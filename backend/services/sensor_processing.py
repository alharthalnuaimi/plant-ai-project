"""
Convert raw ESP32 sensor payloads into the canonical :class:`SensorReading`
shape used by every read path.

Each individual signal (air temperature, soil moisture, light, pH, EC, ...)
is mapped through a small rule-based status function (``low`` / ``normal`` /
``high``) and aggregated into an ``overall_environment_status`` label. The
output is deterministic and dependency-free so the same logic runs in unit
tests, the in-memory MVP store, and the Supabase-backed pipeline.

Thresholds intentionally live as inline constants here. If they grow more
species-specific they should move to ``configs/thresholds.yaml`` so they
can be tuned without a code change.
"""

from __future__ import annotations

from schemas.sensors import SensorInput, SensorReading, SensorStatus, utc_now_iso


def _air_temp_status(temp_c: float) -> str:
    if temp_c < 15:
        return "low"
    if temp_c > 32:
        return "high"
    return "normal"


def _air_humidity_status(humidity: float) -> str:
    if humidity < 40:
        return "low"
    if humidity > 75:
        return "high"
    return "normal"


def _light_status(lux: float) -> str:
    if lux < 200:
        return "low"
    if lux > 5000:
        return "high"
    return "normal"


def _soil_temp_status(temp_c: float) -> str:
    if temp_c < 12:
        return "low"
    if temp_c > 30:
        return "high"
    return "normal"


def _soil_humidity_status(moisture: float) -> str:
    if moisture < 35:
        return "low"
    if moisture > 75:
        return "high"
    return "normal"


def _ph_status(ph: float) -> str:
    if ph < 5.5:
        return "low"
    if ph > 7.5:
        return "high"
    return "normal"


def _ec_status(ec: float) -> str:
    if ec < 0.5:
        return "low"
    if ec > 3.0:
        return "high"
    return "normal"


def _overall_status(parts: list[str]) -> str:
    if "high" in parts or parts.count("low") >= 2:
        return "high_stress"
    if "low" in parts:
        return "moderate_stress"
    return "healthy"


def process_sensor_reading(payload: SensorInput) -> SensorReading:
    # Coalesce None → safe defaults.  Status helpers receive the coalesced
    # value; the "unknown" label is used when the raw reading was None so
    # downstream scoring can tell "sensor offline" from "value is in range".
    _air_t = payload.air_temperature
    _air_h = payload.air_humidity
    _lux   = payload.light_lux
    _soil_t = payload.soil_temperature
    _soil_h = payload.soil_humidity
    _ph     = payload.soil_ph
    _ec     = payload.soil_ec

    air_t = _air_temp_status(_air_t) if _air_t is not None else "unknown"
    air_h = _air_humidity_status(_air_h) if _air_h is not None else "unknown"
    light = _light_status(_lux) if _lux is not None else "unknown"
    soil_t = _soil_temp_status(_soil_t) if _soil_t is not None else "unknown"
    soil_h = _soil_humidity_status(_soil_h) if _soil_h is not None else "unknown"
    ph = _ph_status(_ph) if _ph is not None else "unknown"
    ec = _ec_status(_ec) if _ec is not None else "unknown"

    known_parts = [s for s in [air_t, air_h, light, soil_t, soil_h, ph, ec] if s != "unknown"]
    overall = _overall_status(known_parts) if known_parts else "unknown"

    status = SensorStatus(
        air_temperature_status=air_t,
        air_humidity_status=air_h,
        light_status=light,
        soil_temperature_status=soil_t,
        soil_humidity_status=soil_h,
        ph_status=ph,
        ec_status=ec,
        overall_environment_status=overall,
    )

    uid = (payload.user_id or "demo_user").strip() or "demo_user"
    zid = (payload.zone_id or "zone_alpha").strip() or "zone_alpha"

    return SensorReading(
        user_id=uid,
        zone_id=zid,
        device_id=payload.device_id,
        air_temperature=_air_t if _air_t is not None else 0.0,
        air_humidity=_air_h if _air_h is not None else 0.0,
        light_lux=_lux if _lux is not None else 0.0,
        soil_temperature=_soil_t if _soil_t is not None else 0.0,
        soil_humidity=_soil_h if _soil_h is not None else 0.0,
        soil_ph=_ph if _ph is not None else 0.0,
        soil_ec=_ec if _ec is not None else 0.0,
        timestamp=utc_now_iso(),
        status=status,
    )

