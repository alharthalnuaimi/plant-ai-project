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
    air_t = _air_temp_status(payload.air_temperature)
    air_h = _air_humidity_status(payload.air_humidity)
    light = _light_status(payload.light_lux)
    soil_t = _soil_temp_status(payload.soil_temperature)
    soil_h = _soil_humidity_status(payload.soil_humidity)
    ph = _ph_status(payload.soil_ph)
    ec = _ec_status(payload.soil_ec)
    overall = _overall_status([air_t, air_h, light, soil_t, soil_h, ph, ec])

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
        air_temperature=payload.air_temperature,
        air_humidity=payload.air_humidity,
        light_lux=payload.light_lux,
        soil_temperature=payload.soil_temperature,
        soil_humidity=payload.soil_humidity,
        soil_ph=payload.soil_ph,
        soil_ec=payload.soil_ec,
        timestamp=utc_now_iso(),
        status=status,
    )
