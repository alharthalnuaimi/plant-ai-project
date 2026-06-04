/**
 * Plant health API client — POST /predict only (MVP).
 *
 * Phase 4 (A3): Demo Mode short-circuits.
 *   When `window.plantDemo && window.plantDemo.isOn()` returns true, the
 *   listed fetchers below resolve to canned fixtures from
 *   `demo_fixtures.js` instead of hitting the backend. This lets the UI
 *   look "live" when the ESP32, the backend, or the internet is offline.
 *   Demo mode never persists anything — fixtures are presentation-only.
 */

function _pvDemoOn() {
  return !!(window.plantDemo && typeof window.plantDemo.isOn === "function" && window.plantDemo.isOn());
}
function _pvFx() {
  return (window.plantDemo && window.plantDemo.fixtures) || {};
}

/**
 * POST /predict with full scan-to-zone traceability.
 *
 * @param {File|Blob} file
 * @param {{ zone_id?: string, device_id?: string, user_id?: string, source?: string }} [opts]
 *   - zone_id   : zone slug to attribute the scan to. Defaults to the
 *                 currently selected Garden zone (if any), else
 *                 window.PLANT_ZONE_ID, else "zone_alpha".
 *   - device_id : ESP32 / device slug. Defaults to PLANT_DEVICE_ID.
 *   - user_id   : operator slug. Defaults to PLANT_USER_ID.
 *   - source    : "upload" | "camera" | "chat-camera" | string (purely
 *                 telemetry / shown in result modal; never affects logic).
 */
async function predictPlantImage(file, opts = {}) {
  if (_pvDemoOn() && _pvFx().predictPlantImage) {
    // No backend round-trip; honour overrides for source/plant_id so the
    // result modal still shows the user's chosen zone / scan source.
    const fixture = _pvFx().predictPlantImage();
    if (opts && opts.zone_id)   fixture.zone_id = opts.zone_id;
    if (opts && opts.device_id) fixture.device_id = opts.device_id;
    if (opts && opts.user_id)   fixture.user_id = opts.user_id;
    if (opts && opts.plant_id)  fixture.plant_id = opts.plant_id;
    if (opts && opts.source)    fixture.metadata = Object.assign({}, fixture.metadata, { source: opts.source });
    return Promise.resolve(fixture);
  }
  const base = window.PLANT_API_BASE;
  if (!base) throw new Error("PLANT_API_BASE is not configured");

  const gardenSel =
    (window.plantGarden && typeof window.plantGarden.getSelectedZoneSlug === "function")
      ? window.plantGarden.getSelectedZoneSlug()
      : null;
  const zoneId   = (opts.zone_id   || gardenSel || window.PLANT_ZONE_ID   || "zone_alpha").trim() || "zone_alpha";
  const deviceId = (opts.device_id ||              window.PLANT_DEVICE_ID || "esp32_001").trim() || "esp32_001";
  const userId   = (opts.user_id   ||              window.PLANT_USER_ID   || "demo_user").trim() || "demo_user";
  const source   = (opts.source    || "upload").trim() || "upload";
  // Phase 3 — optional plant identifier (future plant_profiles table).
  // Empty string is allowed; the default keeps demo scans complete.
  const plantId   = (opts.plant_id   != null ? String(opts.plant_id)   : (window.PLANT_ID   || "cucumber_001")).trim();
  const plantName = (opts.plant_name != null ? String(opts.plant_name) : (window.PLANT_NAME || "")).trim();

  const form = new FormData();
  form.append("file", file);
  form.append("user_id", userId);
  form.append("zone_id", zoneId);
  form.append("device_id", deviceId);
  form.append("source", source);
  if (plantId)   form.append("plant_id", plantId);
  if (plantName) form.append("plant_name", plantName);

  const resp = await fetch(`${base}/predict`, {
    method: "POST",
    body: form,
  });

  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const err = await resp.json();
      detail = err.error || err.message || detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
  }

  return resp.json();
}

async function checkBackendHealth() {
  const base = window.PLANT_API_BASE;
  if (!base) return { ok: false, error: "No API base URL" };
  try {
    const resp = await fetch(`${base}/health`, { method: "GET" });
    if (!resp.ok) return { ok: false, error: `HTTP ${resp.status}` };
    const data = await resp.json();
    return { ok: data.status === "ok", data };
  } catch (e) {
    return { ok: false, error: e.message || String(e) };
  }
}

/** GET /models/health — YOLO / Llama load state. */
async function fetchModelsHealth() {
  const base = window.PLANT_API_BASE;
  if (!base) return { ok: false, error: "No API base URL", data: null };
  try {
    const resp = await fetch(`${base}/models/health`, { method: "GET" });
    if (!resp.ok) return { ok: false, error: `HTTP ${resp.status}`, data: null };
    const data = await resp.json();
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e.message || String(e), data: null };
  }
}

/** GET /models/registry — resolved weights path / version metadata. */
async function fetchModelsRegistry() {
  const base = window.PLANT_API_BASE;
  if (!base) return { ok: false, data: null };
  try {
    const resp = await fetch(`${base}/models/registry`, { method: "GET" });
    if (!resp.ok) return { ok: false, data: null };
    return { ok: true, data: await resp.json() };
  } catch (_) {
    return { ok: false, data: null };
  }
}

/** GET /sensor/latest — latest reading for user_id + zone_id + device_id. */
async function fetchSensorLatest() {
  if (_pvDemoOn() && _pvFx().sensorLatestEnvelope) {
    return Promise.resolve(_pvFx().sensorLatestEnvelope());
  }
  const base = window.PLANT_API_BASE;
  if (!base) throw new Error("PLANT_API_BASE is not configured");

  const userId = encodeURIComponent(window.PLANT_USER_ID || "demo_user");
  const zoneId = encodeURIComponent(window.PLANT_ZONE_ID || "zone_alpha");
  const deviceId = encodeURIComponent(window.PLANT_DEVICE_ID || "esp32_001");
  const url = `${base}/sensor/latest?user_id=${userId}&zone_id=${zoneId}&device_id=${deviceId}`;

  const resp = await fetch(url, { method: "GET" });
  if (!resp.ok) {
    let detail = `HTTP ${resp.status}`;
    try {
      const err = await resp.json();
      detail = err.error || err.message || detail;
    } catch (_) {
      /* ignore */
    }
    throw new Error(detail);
  }
  return resp.json();
}

/* ====================================================================
 * UNIFIED SENSOR SOURCE OF TRUTH
 * ------------------------------------------------------------------
 *  Use this from every page (Home, Garden, Profile, Analytics, Chat)
 *  so freshness / mode / live-state are computed in exactly one place.
 *
 *  Returns:
 *    {
 *      ok: bool,                       // backend reachable
 *      source: "live" | "none",        // raw /sensor/latest source
 *      mode: "live" | "stale" | "simulation" | "offline",
 *      freshness: "live" | "stale" | "offline" | "none",
 *      age_seconds: number | null,
 *      user_id, zone_id, device_id,    // active triple
 *      reading: SensorReading | null,
 *    }
 *
 *  Freshness rules (must match backend analytics_store._freshness):
 *    age <= 30s   → live
 *    age <= 300s  → stale  (5 min)
 *    age >  300s  → offline
 *    no reading   → none / simulation
 * ==================================================================== */
const SENSOR_LIVE_MAX_S = 30;
const SENSOR_STALE_MAX_S = 300;

function _sensorEmptyContext(reason) {
  return {
    ok: reason !== "no_base",
    source: "none",
    mode: "simulation",
    freshness: "none",
    age_seconds: null,
    user_id: window.PLANT_USER_ID || "demo_user",
    zone_id: window.PLANT_ZONE_ID || "zone_alpha",
    device_id: window.PLANT_DEVICE_ID || "esp32_001",
    reading: null,
    reason: reason || null,
  };
}

function _computeFreshness(ageSeconds) {
  if (ageSeconds == null || Number.isNaN(ageSeconds)) return "offline";
  if (ageSeconds <= SENSOR_LIVE_MAX_S) return "live";
  if (ageSeconds <= SENSOR_STALE_MAX_S) return "stale";
  return "offline";
}

function _parseIsoTs(iso) {
  if (!iso) return null;
  try {
    return new Date(String(iso).replace("Z", "+00:00")).getTime() / 1000;
  } catch (_) {
    return null;
  }
}

/**
 * Single source of truth. Never throws.
 * Returns a normalized sensor context for any page to consume.
 */
async function fetchLatestSensorContext() {
  const base = window.PLANT_API_BASE;
  // Phase 4 (A3): when Demo Mode is on, fetchSensorLatest() short-
  // circuits to a fixture even with no PLANT_API_BASE, so don't
  // short-circuit on the "no base" branch in that case.
  if (!base && !_pvDemoOn()) return _sensorEmptyContext("no_base");

  let payload = null;
  try {
    payload = await fetchSensorLatest();
  } catch (_) {
    return _sensorEmptyContext("offline");
  }

  if (!payload || !payload.reading) {
    const empty = _sensorEmptyContext("no_reading");
    empty.ok = true;
    return empty;
  }

  const reading = payload.reading;
  // Prefer the backend-computed age if present; otherwise compute locally.
  let age = (typeof payload.age_seconds === "number") ? payload.age_seconds : null;
  if (age == null) {
    const ts = _parseIsoTs(reading.timestamp);
    age = ts ? Math.max(0, Date.now() / 1000 - ts) : null;
  }
  const freshness = payload.freshness && payload.freshness !== "none"
    ? payload.freshness
    : _computeFreshness(age);

  let mode;
  if (freshness === "live") mode = "live";
  else if (freshness === "stale") mode = "stale";
  else mode = "offline";

  return {
    ok: true,
    source: payload.source || "live",
    mode,
    freshness,
    age_seconds: age,
    user_id: reading.user_id || (window.PLANT_USER_ID || "demo_user"),
    zone_id: reading.zone_id || (window.PLANT_ZONE_ID || "zone_alpha"),
    device_id: reading.device_id || (window.PLANT_DEVICE_ID || "esp32_001"),
    reading,
    reason: null,
  };
}

/* In-process cache so multiple panels share a single fetch per tick. */
let _sensorCtxCache = null;
let _sensorCtxAt = 0;
const _SENSOR_CTX_TTL_MS = 1500;

async function getSensorContext(force) {
  const now = Date.now();
  if (!force && _sensorCtxCache && (now - _sensorCtxAt) < _SENSOR_CTX_TTL_MS) {
    return _sensorCtxCache;
  }
  _sensorCtxCache = await fetchLatestSensorContext();
  _sensorCtxAt = now;
  // Broadcast so any page can listen instead of polling.
  try {
    window.dispatchEvent(new CustomEvent("plantvision:sensor-ctx", { detail: _sensorCtxCache }));
  } catch (_) { /* IE fallback not needed */ }
  return _sensorCtxCache;
}

function getLastSensorContext() {
  return _sensorCtxCache;
}

window.plantSensor = {
  fetch: fetchLatestSensorContext,
  get: getSensorContext,
  last: getLastSensorContext,
  computeFreshness: _computeFreshness,
};

/** Analytics dashboard — lightweight aggregation endpoints. */
async function fetchAnalyticsSummary() {
  if (_pvDemoOn() && _pvFx().analyticsSummary) {
    return Promise.resolve(_pvFx().analyticsSummary());
  }
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  const resp = await fetch(`${base}/analytics/summary`);
  return resp.ok ? resp.json() : null;
}

async function fetchAnalyticsHistory(limit = 20) {
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  const resp = await fetch(`${base}/analytics/history?limit=${limit}`);
  return resp.ok ? resp.json() : null;
}

/**
 * Phase 3: rich scan history (DB-backed when possible, memory fallback otherwise).
 * @param {{ zone?: string, status?: string, limit?: number }} [opts]
 * @returns {Promise<{ source: string, total: number, zone: string|null, status_filter: string|null, scans: Array }|null>}
 */
async function fetchScanHistory(opts = {}) {
  if (_pvDemoOn() && _pvFx().scanHistory) {
    return Promise.resolve(_pvFx().scanHistory(opts.limit || 5));
  }
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  const params = new URLSearchParams();
  if (opts.zone)   params.set("zone", opts.zone);
  if (opts.status) params.set("status", opts.status);
  params.set("limit", String(opts.limit || 50));
  const resp = await fetch(`${base}/scans/history?${params.toString()}`);
  return resp.ok ? resp.json() : null;
}

/** Phase 3: full scan detail (incl. sensor snapshot) for the detail modal. */
async function fetchScanDetail(scanId) {
  const base = window.PLANT_API_BASE;
  if (!base || !scanId) return null;
  const resp = await fetch(`${base}/scans/${encodeURIComponent(scanId)}`);
  if (!resp.ok) return null;
  return resp.json();
}

/** Phase 3: per-zone scan counts + status breakdown for Garden badges. */
async function fetchZoneScanCounts() {
  if (_pvDemoOn() && _pvFx().zoneScanCounts) {
    return Promise.resolve(_pvFx().zoneScanCounts());
  }
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  const resp = await fetch(`${base}/scans/zone-counts`);
  return resp.ok ? resp.json() : null;
}

/** Phase 3 correction — Plant Profile aggregate (latest scan, count, history). */
async function fetchPlantProfile(plantId) {
  if (_pvDemoOn() && _pvFx().plantProfile) {
    return Promise.resolve(_pvFx().plantProfile(plantId));
  }
  const base = window.PLANT_API_BASE;
  if (!base || !plantId) return null;
  const resp = await fetch(`${base}/scans/plant/${encodeURIComponent(plantId)}`);
  return resp.ok ? resp.json() : null;
}

/** Resolve a scan thumbnail URL or null if the scan has no saved image. */
function resolveScanImageUrl(scan) {
  if (!scan) return null;
  const base = window.PLANT_API_BASE || "";
  const url = scan.image_url || (scan.metadata && scan.metadata.image_url);
  if (url) return url.startsWith("http") ? url : `${base}${url.startsWith("/") ? "" : "/"}${url}`;
  const path = scan.image_path || (scan.metadata && scan.metadata.saved_path);
  if (!path) return null;
  const norm = path.startsWith("/") ? path : `/${path}`;
  return `${base}${norm}`;
}

async function fetchAnalyticsEvents(limit = 25) {
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  const resp = await fetch(`${base}/analytics/events?limit=${limit}`);
  return resp.ok ? resp.json() : null;
}

async function fetchAnalyticsZones() {
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  const resp = await fetch(`${base}/analytics/zones`);
  return resp.ok ? resp.json() : null;
}

async function fetchAnalyticsInsights() {
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  const resp = await fetch(`${base}/analytics/insights`);
  return resp.ok ? resp.json() : null;
}

/** GET /analytics/garden — live garden map dashboard. */
/** GET /health/plant — rule-based plant health score. */
async function fetchPlantHealth() {
  if (_pvDemoOn() && _pvFx().plantHealth) {
    return Promise.resolve(_pvFx().plantHealth());
  }
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  const userId = encodeURIComponent(window.PLANT_USER_ID || "demo_user");
  const zoneId = encodeURIComponent(window.PLANT_ZONE_ID || "zone_alpha");
  const deviceId = encodeURIComponent(window.PLANT_DEVICE_ID || "esp32_001");
  const url = `${base}/health/plant?user_id=${userId}&zone_id=${zoneId}&device_id=${deviceId}`;
  try {
    const resp = await fetch(url, { method: "GET" });
    if (!resp.ok) return null;
    return resp.json();
  } catch (_) {
    return null;
  }
}

async function fetchGardenDashboard() {
  const base = window.PLANT_API_BASE;
  if (!base) return { ok: false, data: null };
  try {
    const resp = await fetch(`${base}/analytics/garden`, { method: "GET" });
    if (!resp.ok) return { ok: false, data: null };
    return { ok: true, data: await resp.json() };
  } catch (_) {
    return { ok: false, data: null };
  }
}

/* ====== Phase 2 — persistent zones & devices ====== */

async function fetchZones() {
  const base = window.PLANT_API_BASE;
  if (!base) return { ok: false, source: "offline", zones: [] };
  try {
    const resp = await fetch(`${base}/zones`, { method: "GET" });
    if (!resp.ok) return { ok: false, source: "offline", zones: [] };
    const data = await resp.json();
    return { ok: true, source: data.source || "memory", zones: data.zones || [] };
  } catch (_) {
    return { ok: false, source: "offline", zones: [] };
  }
}

async function saveZone(zone) {
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  try {
    const resp = await fetch(`${base}/zones`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(zone),
    });
    if (!resp.ok) return null;
    return resp.json();
  } catch (_) {
    return null;
  }
}

async function deleteZone(slug) {
  const base = window.PLANT_API_BASE;
  if (!base) return false;
  try {
    const resp = await fetch(`${base}/zones/${encodeURIComponent(slug)}`, { method: "DELETE" });
    return resp.ok;
  } catch (_) {
    return false;
  }
}

async function fetchDevices(zoneSlug) {
  const base = window.PLANT_API_BASE;
  if (!base) return { ok: false, source: "offline", devices: [] };
  try {
    const url = zoneSlug
      ? `${base}/devices?zone=${encodeURIComponent(zoneSlug)}`
      : `${base}/devices`;
    const resp = await fetch(url, { method: "GET" });
    if (!resp.ok) return { ok: false, source: "offline", devices: [] };
    const data = await resp.json();
    return { ok: true, source: data.source || "memory", devices: data.devices || [] };
  } catch (_) {
    return { ok: false, source: "offline", devices: [] };
  }
}

async function saveDevice(device) {
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  try {
    const resp = await fetch(`${base}/devices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(device),
    });
    if (!resp.ok) return null;
    return resp.json();
  } catch (_) {
    return null;
  }
}

async function deleteDevice(slug) {
  const base = window.PLANT_API_BASE;
  if (!base) return false;
  try {
    const resp = await fetch(`${base}/devices/${encodeURIComponent(slug)}`, { method: "DELETE" });
    return resp.ok;
  } catch (_) {
    return false;
  }
}

async function fetchDbHealth() {
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  try {
    const resp = await fetch(`${base}/health/db`, { method: "GET" });
    if (!resp.ok) return null;
    return resp.json();
  } catch (_) {
    return null;
  }
}

/**
 * Phase 4 (B1): POST /report (JSON body) — unified plant report used by
 * the Home dashboard's hero score + warnings strip + care card. Falls
 * back to ``null`` on any error so the UI can degrade gracefully.
 *
 * @param {string} plantId
 * @returns {Promise<object|null>}
 */
async function fetchUnifiedReport(plantId) {
  const pid = (plantId || "cucumber_001").trim() || "cucumber_001";
  if (_pvDemoOn() && _pvFx().unifiedReport) {
    return Promise.resolve(_pvFx().unifiedReport(pid));
  }
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  try {
    const resp = await fetch(`${base}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        plant_id: pid,
        user_id: window.PLANT_USER_ID || "demo_user",
        zone_id: window.PLANT_ZONE_ID || "zone_alpha",
        device_id: window.PLANT_DEVICE_ID || "esp32_001",
      }),
    });
    if (!resp.ok) return null;
    return resp.json();
  } catch (_) {
    return null;
  }
}

/**
 * Phase 4 (B2): GET /devices/diagnostics — per-device freshness +
 * retry counters + reachability. Returns ``null`` on any error.
 */
async function fetchDeviceDiagnostics() {
  const base = window.PLANT_API_BASE;
  if (!base) return null;
  try {
    const resp = await fetch(`${base}/devices/diagnostics`, { method: "GET" });
    if (!resp.ok) return null;
    return resp.json();
  } catch (_) {
    return null;
  }
}
