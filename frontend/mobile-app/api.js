/**
 * Plant health API client — POST /predict only (MVP).
 */

async function predictPlantImage(file) {
  const base = window.PLANT_API_BASE;
  if (!base) throw new Error("PLANT_API_BASE is not configured");

  const form = new FormData();
  form.append("file", file);
  form.append("user_id", window.PLANT_USER_ID || "demo_user");
  form.append("zone_id", window.PLANT_ZONE_ID || "zone_alpha");

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

/** Analytics dashboard — lightweight aggregation endpoints. */
async function fetchAnalyticsSummary() {
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
