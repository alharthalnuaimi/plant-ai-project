"""In-memory analytics for MVP dashboard (scans, events, trends)."""

from __future__ import annotations

import logging
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger("plantvision.analytics_store")

from schemas.analytics import (
    AIInsight,
    AnalyticsEvent,
    AnalyticsSummary,
    ScanHistoryItem,
    ZoneHealthSummary,
)
from schemas.garden import (
    GardenActivityItem,
    GardenDashboard,
    GardenDevice,
    GardenInsight,
    GardenSummary,
    GardenZone,
)

def _scan_outcomes_from_scans(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not scans:
        return [
            {"label": "Awaiting scans", "count": 0, "pct": 100.0, "tone": "neutral"},
        ]
    counts = {"PASS": 0, "WARN": 0, "CRITICAL": 0}
    for s in scans:
        st = s.get("status", "WARN")
        if st in counts:
            counts[st] += 1
    total = len(scans)
    healthy = sum(1 for s in scans if _is_healthy_disease(s["disease"]))
    slices = []
    if healthy:
        pct = round((healthy / total) * 100, 1)
        slices.append({"label": "Healthy", "count": healthy, "pct": pct, "tone": "pass"})
    diseased = total - healthy
    if diseased:
        warn = counts["WARN"] + counts["CRITICAL"]
        if warn:
            slices.append(
                {
                    "label": "Diseased / at risk",
                    "count": warn,
                    "pct": round((warn / total) * 100, 1),
                    "tone": "warn" if counts["CRITICAL"] == 0 else "crit",
                }
            )
    if not slices:
        slices.append({"label": "Scans recorded", "count": total, "pct": 100.0, "tone": "pass"})
    return slices
from schemas.contracts import VisionResult
from schemas.sensors import SensorReading
from services import sensor_store
from services import persistence

_MAX_SCANS = 500
_MAX_EVENTS = 120
_MAX_SPARK = 24
_SCAN_SEQ_START = 4821

_scans: deque[dict[str, Any]] = deque(maxlen=_MAX_SCANS)
_events: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
_sparklines: dict[str, dict[str, deque[float]]] = {}
_scan_counter = _SCAN_SEQ_START

_ZONE_LABELS: dict[str, str] = {
    "zone_alpha": "Zone Alpha",
    "zone_beta": "Zone Beta",
    "zone_gamma": "Zone Gamma",
}


def _now() -> float:
    return time.time()


def _reading_ts(reading: SensorReading) -> float:
    try:
        return datetime.fromisoformat(reading.timestamp.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return _now()


def _zone_label(zone_id: str) -> str:
    return _ZONE_LABELS.get(zone_id, zone_id.replace("_", " ").title())


def _is_healthy_disease(disease: str) -> bool:
    d = (disease or "").lower()
    return any(x in d for x in ("healthy", "normal", "no disease", "none"))


def _scan_status(disease: str, confidence: float, accepted: bool) -> str:
    if _is_healthy_disease(disease):
        return "PASS"
    if confidence >= 0.9 or (not accepted and confidence >= 0.7):
        return "CRITICAL"
    return "WARN"


def _push_event(
    event_type: str,
    message: str,
    *,
    zone_id: str | None = None,
    device_id: str | None = None,
) -> None:
    _events.appendleft(
        {
            "id": uuid.uuid4().hex[:10],
            "timestamp": _now(),
            "event_type": event_type,
            "message": message,
            "zone_id": zone_id,
            "device_id": device_id,
        }
    )
    persistence.persist_event(
        event_type=event_type,
        message=message,
        zone_slug=zone_id,
        device_slug=device_id,
    )


def _spark_key(user_id: str, zone_id: str) -> str:
    return f"{user_id}:{zone_id}"


def _append_spark(user_id: str, zone_id: str, reading: SensorReading) -> None:
    key = _spark_key(user_id, zone_id)
    if key not in _sparklines:
        _sparklines[key] = {
            "air_temperature": deque(maxlen=_MAX_SPARK),
            "air_humidity": deque(maxlen=_MAX_SPARK),
            "soil_ph": deque(maxlen=_MAX_SPARK),
            "soil_ec": deque(maxlen=_MAX_SPARK),
        }
    buckets = _sparklines[key]
    buckets["air_temperature"].append(float(reading.air_temperature))
    buckets["air_humidity"].append(float(reading.air_humidity))
    buckets["soil_ph"].append(float(reading.soil_ph))
    buckets["soil_ec"].append(float(reading.soil_ec))


def record_scan(result: VisionResult) -> ScanHistoryItem:
    global _scan_counter
    _scan_counter += 1
    ts = _now()
    status = _scan_status(result.disease, result.confidence, result.accepted)
    item = {
        "scan_id": f"#{_scan_counter}",
        "user_id": result.user_id,
        "zone_id": result.zone_id,
        "disease": result.disease,
        "confidence": float(result.confidence),
        "status": status,
        "inference_ms": float(result.inference_ms),
        "timestamp": ts,
        "accepted": result.accepted,
    }
    _scans.appendleft(item)
    conf_pct = result.confidence * 100
    _push_event(
        "scan",
        f"Scan complete — {result.disease} ({conf_pct:.1f}%)",
        zone_id=result.zone_id,
    )
    if status == "CRITICAL":
        _push_event(
            "alert",
            f"High-risk detection in {_zone_label(result.zone_id)}",
            zone_id=result.zone_id,
        )
    if result.health:
        _push_event(
            "ai",
            f"Plant health score {result.health.plant_health}% — {result.health.recommendation[:80]}",
            zone_id=result.zone_id,
        )
    persistence.persist_scan(result)
    return ScanHistoryItem(**item)


def record_sensor(reading: SensorReading) -> None:
    _append_spark(reading.user_id, reading.zone_id, reading)
    persistence.persist_sensor(reading)
    label = _zone_label(reading.zone_id)
    _push_event(
        "sensor",
        f"{label} sensor updated",
        zone_id=reading.zone_id,
        device_id=reading.device_id,
    )
    if reading.air_humidity < 35:
        _push_event(
            "alert",
            f"Low humidity warning — {label} ({reading.air_humidity:.0f}%)",
            zone_id=reading.zone_id,
            device_id=reading.device_id,
        )
    if reading.soil_humidity < 28:
        _push_event(
            "alert",
            f"Soil moisture low — {label} ({reading.soil_humidity:.0f}%)",
            zone_id=reading.zone_id,
            device_id=reading.device_id,
        )
    if reading.air_temperature > 32:
        _push_event(
            "alert",
            f"Temperature stress — {label} ({reading.air_temperature:.1f}°C)",
            zone_id=reading.zone_id,
            device_id=reading.device_id,
        )


def record_device_connected(device_id: str, zone_id: str) -> None:
    _push_event(
        "device",
        f"Device {device_id} connected",
        zone_id=zone_id,
        device_id=device_id,
    )


async def hydrate_from_db(limit: int = 200) -> int:
    """Re-populate the in-memory analytics deque from `scan_results` and `sensor_readings`.

    Called at startup so the dashboard / Home log / Assistant context all
    survive a backend restart when persistence is enabled. Returns the
    number of scans loaded.
    """

    global _scan_counter
    if _scans:  # already populated this process
        return 0

    # 1. Hydrate scan history
    try:
        from repositories import scans_repo  # local import to avoid cycles
    except Exception:  # noqa: BLE001
        scans_repo = None

    loaded = 0
    if scans_repo:
        try:
            rows = await scans_repo.recent(limit=limit)
        except Exception:  # noqa: BLE001
            rows = []

        # rows come back newest-first; reverse so the deque order matches the
        # natural arrival order (older items at the right end).
        for row in reversed(rows):
            try:
                created = row.get("created_at")
                if isinstance(created, datetime):
                    ts = created.timestamp()
                else:
                    ts = _now()
                disease = row.get("disease") or "Unknown"
                confidence = float(row.get("confidence") or 0.0)
                accepted = bool(row.get("accepted") if row.get("accepted") is not None else True)
                _scan_counter += 1
                _scans.appendleft({
                    "scan_id": f"#{_scan_counter}",
                    "user_id": row.get("user_slug") or "demo_user",
                    "zone_id": row.get("zone_slug") or "zone_alpha",
                    "disease": disease,
                    "confidence": confidence,
                    "status": _scan_status(disease, confidence, accepted),
                    "inference_ms": float(row.get("inference_ms") or 0.0),
                    "timestamp": ts,
                    "accepted": accepted,
                })
                loaded += 1
            except Exception:  # noqa: BLE001 — never let one bad row break boot
                continue

    # 2. Hydrate sensor readings history and warm up cache
    try:
        from repositories import sensor_repo
        from services.sensor_store import save_reading
        from schemas.sensors import SensorInput
        from services.sensor_processing import process_sensor_reading
    except Exception as exc:  # noqa: BLE001
        log.warning("Sensor hydration imports failed: %s", exc)
        return loaded

    try:
        sensor_rows = await sensor_repo.recent_readings(limit=limit)
        for row in sensor_rows:
            try:
                payload = SensorInput(
                    user_id=row.get("user_slug") or "demo_user",
                    zone_id=row.get("zone_slug") or "zone_alpha",
                    device_id=row.get("device_slug") or "esp32_001",
                    air_temperature=float(row["air_temp"]),
                    air_humidity=float(row["air_humidity"]),
                    light_lux=float(row.get("lux") or 0),
                    soil_temperature=float(row["soil_temp"]),
                    soil_humidity=float(row["soil_moisture"]),
                    soil_ph=float(row["ph"]),
                    soil_ec=float(row["ec"]),
                )
                reading = process_sensor_reading(payload)
                recorded_at = row.get("recorded_at")
                if isinstance(recorded_at, datetime):
                    ts = recorded_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()
                    reading = reading.model_copy(update={"timestamp": ts})
                
                # Update in-memory cache and append to sparklines
                save_reading(reading)
                _append_spark(reading.user_id, reading.zone_id, reading)
            except Exception as exc:  # noqa: BLE001
                log.warning("Failed to hydrate sensor reading row: %s", exc)
                continue
        if sensor_rows:
            log.info("Hydrated %d sensor reading(s) from Supabase into in-memory analytics", len(sensor_rows))
    except Exception as exc:  # noqa: BLE001
        log.warning("Sensor hydration failed: %s", exc)

    return loaded


def _demo_summary() -> AnalyticsSummary:
  days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
  return AnalyticsSummary(
        detection_rate=18.5,
        avg_confidence=0.912,
        avg_inference_ms=420.0,
        connected_devices=1,
        active_zones=1,
        total_scans=0,
        scans_today=0,
        source="demo",
        top_diseases=[
            {"name": "Awaiting scans", "pct": 100.0},
        ],
        activity_by_day=[{"day": d, "count": 0, "pct": 0.0} for d in days],
        confidence_series=[0.88, 0.9, 0.91, 0.89, 0.92, 0.9, 0.91],
        scan_outcomes=[
            {"label": "Demo — no scans", "count": 0, "pct": 100.0, "tone": "neutral"},
        ],
        pass_rate=0.0,
    )


_UNCLASSIFIED_DISEASES = {"unknown", "pending", "pending analysis", "unclassified", "n/a"}


def _has_valid_confidence(s: dict[str, Any]) -> bool:
    """A scan has a usable confidence value (real positive number)."""
    conf = s.get("confidence")
    try:
        return conf is not None and float(conf) > 0.0
    except (TypeError, ValueError):
        return False


def _is_classified(s: dict[str, Any]) -> bool:
    """The scan has a classified disease (not empty / 'Unknown' / placeholder)."""
    d = (s.get("disease") or "").strip().lower()
    return bool(d) and d not in _UNCLASSIFIED_DISEASES


def _is_valid_prediction(s: dict[str, Any]) -> bool:
    """Phase 3 polish — combined predicate kept for backward compatibility.
    Total scan count still includes ALL scans regardless of this filter.
    """
    return _is_classified(s) and _has_valid_confidence(s)


def get_summary() -> AnalyticsSummary:
    scans = list(_scans)
    if not scans:
        return _demo_summary()

    total = len(scans)
    # Phase 3 — per the correction pass:
    # - avg_confidence: include any scan with a real positive confidence
    #   (so legitimate 0.35-conf "Diseased" detections still contribute).
    # - detection_rate: include only scans with a classified disease
    #   (so "Unknown" / placeholder rows don't pollute the disease ratio).
    # - total_scans still counts EVERYTHING for the user-facing count.
    conf_pool = [s for s in scans if _has_valid_confidence(s)]
    cls_pool = [s for s in scans if _is_classified(s)]
    avg_conf = round(sum(float(s["confidence"]) for s in conf_pool) / len(conf_pool), 4) if conf_pool else 0.0
    diseased = sum(1 for s in cls_pool if not _is_healthy_disease(s["disease"]))
    detection_rate = round((diseased / len(cls_pool)) * 100, 1) if cls_pool else 0.0
    avg_ms = round(sum(s["inference_ms"] for s in scans) / total, 1)

    readings = sensor_store.list_all_readings()
    connected = len(readings) or 1
    active_cutoff = _now() - 1800
    active_zones = len(
        {r.zone_id for r in readings if _reading_ts(r) >= active_cutoff}
    ) or len({s["zone_id"] for s in scans[:20]})

    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    ).timestamp()
    scans_today = sum(1 for s in scans if s["timestamp"] >= today_start)

    disease_counts: dict[str, int] = {}
    for s in cls_pool:  # only count scans with a classified disease
        d = s["disease"]
        if _is_healthy_disease(d):
            continue
        disease_counts[d] = disease_counts.get(d, 0) + 1
    top_sorted = sorted(disease_counts.items(), key=lambda x: -x[1])[:6]
    top_total = sum(c for _, c in top_sorted) or 1
    top_diseases = [
        {"name": name, "pct": round((c / top_total) * 100, 1)}
        for name, c in top_sorted
    ] or [{"name": "No issues detected", "pct": 100.0}]

    activity_by_day = _activity_buckets(scans)
    conf_series = [round(s["confidence"], 4) for s in reversed(scans[-20:])]
    pass_count = sum(1 for s in scans if s["status"] == "PASS")
    pass_rate = round((pass_count / total) * 100, 1) if total else 0.0

    return AnalyticsSummary(
        detection_rate=detection_rate,
        avg_confidence=avg_conf,
        avg_inference_ms=avg_ms,
        connected_devices=connected,
        active_zones=max(active_zones, 1),
        total_scans=total,
        scans_today=scans_today,
        source="live",
        top_diseases=top_diseases,
        activity_by_day=activity_by_day,
        confidence_series=conf_series,
        scan_outcomes=_scan_outcomes_from_scans(scans),
        pass_rate=pass_rate,
    )


def _activity_buckets(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    counts = [0] * 7
    now = datetime.now(timezone.utc)
    for s in scans:
        dt = datetime.fromtimestamp(s["timestamp"], tz=timezone.utc)
        days_ago = (now.date() - dt.date()).days
        if 0 <= days_ago < 7:
            idx = (now.weekday() - days_ago) % 7
            counts[idx] += 1
    mx = max(counts) or 0
    total_week = sum(counts)
    out = []
    for i in range(7):
        c = counts[i]
        if mx > 0:
            pct = round((c / mx) * 100, 1)
            display = max(pct, 12.0) if c > 0 else 0.0
        else:
            pct = 0.0
            display = 8.0
        out.append({"day": labels[i], "count": c, "pct": display})
    return out


def get_latest_scan(
    user_id: str | None = None,
    zone_id: str | None = None,
) -> dict[str, Any] | None:
    for item in _scans:
        if user_id and item.get("user_id") != user_id:
            continue
        if zone_id and item.get("zone_id") != zone_id:
            continue
        return dict(item)
    return None


def get_history(limit: int = 20) -> list[ScanHistoryItem]:
    return [ScanHistoryItem(**s) for s in list(_scans)[:limit]]


def _demo_history() -> list[ScanHistoryItem]:
    base = _now()
    demos = [
        ("#4821", "zone_alpha", "Healthy", 0.964, "PASS", 380),
        ("#4820", "zone_alpha", "Leaf Spot", 0.871, "WARN", 410),
        ("#4819", "zone_beta", "Healthy", 0.991, "PASS", 395),
    ]
    out: list[ScanHistoryItem] = []
    for i, (sid, zid, dis, conf, st, ms) in enumerate(demos):
        out.append(
            ScanHistoryItem(
                scan_id=sid,
                user_id="demo_user",
                zone_id=zid,
                disease=dis,
                confidence=conf,
                status=st,
                inference_ms=float(ms),
                timestamp=base - (i + 1) * 900,
                accepted=st == "PASS",
            )
        )
    return out


def get_events(limit: int = 30) -> list[AnalyticsEvent]:
    return [AnalyticsEvent(**e) for e in list(_events)[:limit]]


def _demo_events() -> list[AnalyticsEvent]:
    base = _now()
    msgs = [
        ("sensor", "Zone Alpha sensor updated", "zone_alpha", None),
        ("scan", "Scan complete — Healthy (96.4%)", "zone_alpha", None),
        ("alert", "Soil humidity warning — Zone Beta", "zone_beta", None),
        ("ai", "AI recommendation generated", "zone_alpha", None),
        ("device", "Device esp32_001 connected", "zone_alpha", "esp32_001"),
    ]
    return [
        AnalyticsEvent(
            id=f"demo{i}",
            timestamp=base - i * 120,
            event_type=t[0],
            message=t[1],
            zone_id=t[2],
            device_id=t[3],
        )
        for i, t in enumerate(msgs)
    ]


def _zone_status(reading: SensorReading | None) -> tuple[str, str]:
    if reading is None:
        return "WARNING", "Awaiting sensor data"
    if reading.air_temperature > 32 or reading.soil_humidity < 25:
        return "CRITICAL", "Environmental stress"
    if reading.air_temperature > 28 or reading.air_humidity < 40 or reading.soil_ph < 5.8:
        return "WARNING", "Monitor closely"
    return "HEALTHY", "Stable readings"


def get_zones() -> list[ZoneHealthSummary]:
    readings = {r.zone_id: r for r in sensor_store.list_all_readings()}
    scan_zones = {s["zone_id"] for s in list(_scans)[:100]}
    zone_ids = set(readings.keys()) | scan_zones
    if not zone_ids:
        return []

    out: list[ZoneHealthSummary] = []
    for zid in sorted(zone_ids):
        reading = readings.get(zid)
        has_scan = zid in scan_zones
        if not reading and not has_scan:
            continue

        if reading:
            status, note = _zone_status(reading)
            key = _spark_key(reading.user_id, zid)
        else:
            status, note = "WARNING", "Scan data only — awaiting sensor"
            key = _spark_key("demo_user", zid)

        sparks = _sparklines.get(key, {})
        spark_dict = {k: list(v) for k, v in sparks.items()} if sparks else {}
        label = _zone_label(zid)
        is_demo = reading is None

        out.append(
            ZoneHealthSummary(
                zone_id=zid,
                label=label,
                is_demo=is_demo,
                air_temperature=float(reading.air_temperature) if reading else None,
                air_humidity=float(reading.air_humidity) if reading else None,
                soil_ph=float(reading.soil_ph) if reading else None,
                soil_ec=float(reading.soil_ec) if reading else None,
                status=status,
                status_note=note,
                last_updated=_reading_ts(reading) if reading else None,
                sparklines=spark_dict,
            )
        )
    return out


def get_insights() -> list[AIInsight]:
    insights: list[AIInsight] = []
    scans = list(_scans)
    readings = sensor_store.list_all_readings()

    if scans:
        latest = scans[0]
        if not _is_healthy_disease(latest["disease"]) and latest["confidence"] >= 0.75:
            label = _zone_label(latest["zone_id"])
            insights.append(
                AIInsight(
                    insight=f"{label} shows {latest['disease']} with "
                    f"{latest['confidence'] * 100:.1f}% confidence.",
                    recommendation="Inspect affected leaves and isolate the zone if symptoms spread.",
                    severity="critical" if latest["status"] == "CRITICAL" else "warning",
                )
            )

    for r in readings:
        label = _zone_label(r.zone_id)
        if r.air_temperature > 30:
            insights.append(
                AIInsight(
                    insight=f"{label} shows increasing temperature stress ({r.air_temperature:.1f}°C).",
                    recommendation="Increase ventilation or shade and monitor EC over the next hour.",
                    severity="warning",
                )
            )
        if r.soil_humidity < 30:
            insights.append(
                AIInsight(
                    insight=f"{label} soil moisture is low ({r.soil_humidity:.0f}%).",
                    recommendation="Increase irrigation and recheck humidity within 30 minutes.",
                    severity="warning",
                )
            )
        if r.soil_ph < 5.8 or r.soil_ph > 7.5:
            insights.append(
                AIInsight(
                    insight=f"{label} soil pH is {r.soil_ph:.1f} (outside optimal 6.0–7.0).",
                    recommendation="Adjust nutrient solution and retest pH after the next watering cycle.",
                    severity="warning",
                )
            )

    if not insights:
        insights.append(
            AIInsight(
                insight="All monitored zones are within normal parameters.",
                recommendation="Continue scheduled scans and sensor polling.",
                severity="info",
            )
        )
    return insights[:4]


def _freshness(ts: float | None) -> str:
    """Unified freshness rule (must match the frontend helper).

    - live    : age <= 30 seconds
    - stale   : 30 < age <= 300 seconds (5 minutes)
    - offline : age > 300 seconds or no reading at all
    """

    if ts is None:
        return "offline"
    age = _now() - ts
    if age <= 30:
        return "live"
    if age <= 300:
        return "stale"
    return "offline"


def _device_insights(r: SensorReading) -> list[GardenInsight]:
    out: list[GardenInsight] = []
    if r.air_humidity < 40:
        out.append(GardenInsight(label="Humidity low", tone="warn"))
    elif r.air_humidity > 75:
        out.append(GardenInsight(label="Humidity high", tone="warn"))
    else:
        out.append(GardenInsight(label="Humidity normal", tone="pass"))
    if r.soil_humidity < 28:
        out.append(GardenInsight(label="Soil dry", tone="crit"))
    elif r.soil_humidity < 35:
        out.append(GardenInsight(label="Soil moisture low", tone="warn"))
    else:
        out.append(GardenInsight(label="Soil moisture OK", tone="pass"))
    if r.soil_ph < 5.8:
        out.append(GardenInsight(label="pH acidic", tone="warn"))
    elif r.soil_ph > 7.5:
        out.append(GardenInsight(label="pH alkaline", tone="warn"))
    else:
        out.append(GardenInsight(label="pH optimal", tone="pass"))
    if r.soil_ec > 3.0:
        out.append(GardenInsight(label="EC elevated", tone="warn"))
    elif r.soil_ec < 1.0:
        out.append(GardenInsight(label="EC low", tone="warn"))
    else:
        out.append(GardenInsight(label="EC normal", tone="pass"))
    if r.air_temperature > 32:
        out.append(GardenInsight(label="Heat stress", tone="crit"))
    return out[:5]


def _device_status(r: SensorReading) -> str:
    if r.air_temperature > 32 or r.soil_humidity < 25:
        return "CRITICAL"
    if r.air_temperature > 28 or r.air_humidity < 40:
        return "WARNING"
    return "HEALTHY"


def _activity_severity(event_type: str, message: str) -> str:
    if event_type == "alert" or "critical" in message.lower() or "disease" in message.lower():
        return "crit"
    if event_type in ("sensor", "scan") and ("warning" in message.lower() or "low" in message.lower()):
        return "warn"
    return "info"


def get_garden() -> GardenDashboard:
    readings = sensor_store.list_all_readings()
    has_live = bool(readings) or bool(_scans)
    source = "live" if has_live else "demo"

    zone_summaries = get_zones()
    devices_by_zone: dict[str, list[SensorReading]] = {}
    for r in readings:
        devices_by_zone.setdefault(r.zone_id, []).append(r)

    garden_zones: list[GardenZone] = []
    for z in zone_summaries:
        z_devices = devices_by_zone.get(z.zone_id, [])
        st = z.status
        if not z_devices and z.is_demo:
            st = "OFFLINE"
        garden_zones.append(
            GardenZone(
                zone_id=z.zone_id,
                label=z.label,
                status=st,
                status_note=z.status_note,
                device_count=len(z_devices),
                last_updated=z.last_updated,
                air_temperature=z.air_temperature,
                air_humidity=z.air_humidity,
                soil_ph=z.soil_ph,
                soil_ec=z.soil_ec,
            )
        )

    garden_devices: list[GardenDevice] = []
    for r in readings:
        ts = _reading_ts(r)
        fresh = _freshness(ts)
        st = _device_status(r) if fresh != "offline" else "OFFLINE"
        key = _spark_key(r.user_id, r.zone_id)
        sparks = _sparklines.get(key, {})
        spark_dict = {k: list(v) for k, v in sparks.items()} if sparks else {}
        garden_devices.append(
            GardenDevice(
                device_id=r.device_id,
                zone_id=r.zone_id,
                user_id=r.user_id,
                status=st,
                freshness=fresh,
                last_updated=ts,
                air_temperature=float(r.air_temperature),
                air_humidity=float(r.air_humidity),
                light_lux=float(r.light_lux),
                soil_temperature=float(r.soil_temperature),
                soil_humidity=float(r.soil_humidity),
                soil_ph=float(r.soil_ph),
                soil_ec=float(r.soil_ec),
                insights=_device_insights(r),
                sparklines=spark_dict,
            )
        )

    healthy = sum(1 for z in garden_zones if z.status == "HEALTHY")
    warning = sum(1 for z in garden_zones if z.status == "WARNING")
    critical = sum(1 for z in garden_zones if z.status == "CRITICAL")
    offline_dev = sum(1 for d in garden_devices if d.freshness == "offline")

    alerts = get_events(limit=15) if has_live else _demo_events()[:15]
    activity: list[GardenActivityItem] = []
    if has_live:
        for ev in get_events(limit=20):
            activity.append(
                GardenActivityItem(
                    timestamp=ev.timestamp,
                    message=ev.message,
                    zone_id=ev.zone_id,
                    device_id=ev.device_id,
                    severity=_activity_severity(ev.event_type, ev.message),
                )
            )
    if not activity and not has_live:
        base = _now()
        activity = [
            GardenActivityItem(
                timestamp=base - 180,
                message="Zone Alpha sensor updated",
                zone_id="zone_alpha",
                severity="info",
            ),
            GardenActivityItem(
                timestamp=base - 120,
                message="Awaiting live sensor stream",
                severity="info",
            ),
        ]

    return GardenDashboard(
        source=source,
        summary=GardenSummary(
            healthy=healthy,
            warning=warning,
            critical=critical,
            offline_devices=offline_dev,
        ),
        zones=garden_zones,
        devices=garden_devices,
        alerts=alerts,
        activity=activity[:20],
    )
