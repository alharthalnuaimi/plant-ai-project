/**
 * Plant health API client — POST /predict only (MVP).
 */

async function predictPlantImage(file) {
  const base = window.PLANT_API_BASE;
  if (!base) throw new Error("PLANT_API_BASE is not configured");

  const form = new FormData();
  form.append("file", file);

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

/** GET /sensor/latest — latest ESP32 reading or source "none". */
async function fetchSensorLatest() {
  const base = window.PLANT_API_BASE;
  if (!base) throw new Error("PLANT_API_BASE is not configured");

  const resp = await fetch(`${base}/sensor/latest`, { method: "GET" });
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
