/**
 * PlantVision Control Center — live settings, status, localStorage persistence.
 */
(function () {
  const STORAGE_KEY = "pv-settings";
  const FRONTEND_VERSION = "6.0.0";
  const POLL_MS = 5000;
  const PH_ABS_MIN = 4;
  const PH_ABS_MAX = 9;
  const PH_MIN_GAP = 0.4;

  const DEFAULTS = {
    confidenceThreshold: 85,
    autoScan: false,
    hudOverlay: true,
    soundEffects: true,
    resolution: 1080,
    flashMode: "auto",
    multiAngle: false,
    notifications: true,
    animations: true,
    particles: true,
    compactMode: false,
    sensorPollSec: 5,
    tempAlertC: 32,
    humidityAlertLow: 30,
    soilMoistureAlertLow: 25,
    phMin: 5.5,
    phMax: 7.5,
    ecAlertHigh: 3.0,
    autoCalibrate: true,
  };

  let settings = loadSettings();
  let statusTimer = null;
  let lastSensorTs = 0;
  let lastScanTs = 0;

  function loadSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return { ...DEFAULTS };
      return { ...DEFAULTS, ...JSON.parse(raw) };
    } catch (_) {
      return { ...DEFAULTS };
    }
  }

  function saveSettings(partial, toastMsg) {
    settings = { ...settings, ...partial };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    applySettings();
    if (toastMsg) showToast(toastMsg);
    window.dispatchEvent(new CustomEvent("plantvision:settings-changed", { detail: { ...settings } }));
  }

  function getSettings() {
    return { ...settings };
  }

  function showToast(message) {
    const root = document.getElementById("pv-toast-root");
    if (!root) return;
    const el = document.createElement("div");
    el.className = "pv-toast";
    el.textContent = message;
    root.appendChild(el);
    requestAnimationFrame(() => el.classList.add("pv-toast-show"));
    setTimeout(() => {
      el.classList.remove("pv-toast-show");
      setTimeout(() => el.remove(), 320);
    }, 2600);
  }

  function fmtAgo(sec) {
    if (!sec || sec <= 0) return "never";
    const s = Math.max(0, Math.floor(Date.now() / 1000 - sec));
    if (s < 60) return s + "s ago";
    if (s < 3600) return Math.floor(s / 60) + "m ago";
    return Math.floor(s / 3600) + "h ago";
  }

  function fmtUptime(sec) {
    if (sec == null || sec < 0) return "—";
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    return h + "h " + m + "m";
  }

  function setStatusRow(key, state, label) {
    const dot = document.getElementById("st-dot-" + key);
    const val = document.getElementById("st-val-" + key);
    if (dot) {
      dot.className = "status-dot status-" + state;
    }
    if (val) val.textContent = label;
  }

  async function refreshSystemStatus() {
    const tag = document.getElementById("settings-live-tag");
    const polled = document.getElementById("status-polled-at");
    const envMode = document.getElementById("about-env-mode");

    let backendOk = false;
    let uptimeSec = null;
    let yoloLoaded = false;
    let yoloVersion = "—";
    let modelFile = "—";
    let sensorLive = false;
    let sensorFw = "—";
    let analyticsOk = false;
    let envLabel = "Offline";

    if (typeof checkBackendHealth === "function") {
      const h = await checkBackendHealth();
      backendOk = h.ok;
      if (h.ok && h.data && h.data.uptime_sec != null) {
        uptimeSec = h.data.uptime_sec;
      }
    }

    if (backendOk && typeof fetchModelsHealth === "function") {
      const mh = await fetchModelsHealth();
      if (mh.ok && mh.data) {
        yoloLoaded = Boolean(mh.data.vision_loaded);
        yoloVersion = mh.data.vision_version || mh.data.active_versions?.vision || "loaded";
      }
    }

    if (backendOk && typeof fetchModelsRegistry === "function") {
      const reg = await fetchModelsRegistry();
      if (reg.ok && reg.data && reg.data.resolved_weights) {
        const w = reg.data.resolved_weights;
        modelFile = String(w).split(/[/\\]/).pop() || w;
      }
    }

    if (backendOk && typeof fetchSensorLatest === "function") {
      try {
        const data = await fetchSensorLatest();
        if (data.source === "live" && data.reading) {
          sensorLive = true;
          const ts = data.reading.timestamp;
          if (typeof ts === "number") lastSensorTs = ts;
          else if (ts) lastSensorTs = Math.floor(new Date(ts).getTime() / 1000);
          else lastSensorTs = Math.floor(Date.now() / 1000);
          const meta = data.reading.metadata || data.reading.meta || {};
          sensorFw = meta.firmware || meta.firmware_version || "ESP32 live";
        } else {
          sensorFw = "No live reading";
        }
      } catch (_) {
        sensorFw = "Unreachable";
      }
    }

    if (backendOk && typeof fetchAnalyticsSummary === "function") {
      try {
        const sum = await fetchAnalyticsSummary();
        analyticsOk = Boolean(sum);
        if (sum && sum.source) {
          envLabel = sum.source === "live" ? "Live" : "Demo";
        }
      } catch (_) {
        analyticsOk = false;
      }
    }

    if (!backendOk) envLabel = "Offline";
    else if (envLabel === "Offline") envLabel = sensorLive ? "Live" : "Demo";

    setStatusRow("backend", backendOk ? "ok" : "off", backendOk ? "Online" : "Offline");
    setStatusRow(
      "yolo",
      backendOk ? (yoloLoaded ? "ok" : "warn") : "off",
      backendOk ? (yoloLoaded ? "Loaded" : "Not loaded") : "—"
    );
    setStatusRow(
      "sensor",
      backendOk ? (sensorLive ? "ok" : "warn") : "off",
      backendOk ? (sensorLive ? "Connected" : "No live sensor") : "—"
    );
    setStatusRow(
      "analytics",
      backendOk ? (analyticsOk ? "ok" : "warn") : "off",
      backendOk ? (analyticsOk ? "Running" : "Unavailable") : "—"
    );

    let camState = "unknown";
    let camLabel = "Checking…";
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      camState = "off";
      camLabel = "Unsupported";
    } else if (navigator.permissions && navigator.permissions.query) {
      try {
        const perm = await navigator.permissions.query({ name: "camera" });
        if (perm.state === "granted") {
          camState = "ok";
          camLabel = "Granted";
        } else if (perm.state === "denied") {
          camState = "off";
          camLabel = "Blocked";
        } else {
          camState = "warn";
          camLabel = "Not granted";
        }
      } catch (_) {
        camState = "warn";
        camLabel = "Prompt on scan";
      }
    } else {
      camState = "warn";
      camLabel = "Prompt on scan";
    }
    setStatusRow("camera", camState, camLabel);

    const hbSensor = document.getElementById("hb-sensor");
    const hbScan = document.getElementById("hb-scan");
    const hbAnalytics = document.getElementById("hb-analytics");
    if (hbSensor) hbSensor.textContent = "Last sensor: " + (sensorLive ? fmtAgo(lastSensorTs) : "no live sensor");
    if (hbScan) {
      const ts = lastScanTs || parseInt(localStorage.getItem("pv-last-scan-ts") || "0", 10);
      hbScan.textContent = "Last scan: " + fmtAgo(ts);
    }
    if (hbAnalytics) {
      const at =
        window.plantAnalytics && typeof window.plantAnalytics.getLastRefreshAt === "function"
          ? window.plantAnalytics.getLastRefreshAt()
          : 0;
      hbAnalytics.textContent = at ? "Analytics: " + fmtAgo(Math.floor(at / 1000)) : "Analytics: —";
    }

    if (polled) polled.textContent = "Updated " + new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    if (tag) {
      tag.textContent = backendOk ? "● Live" : "● Offline";
      tag.style.color = backendOk ? "var(--sage)" : "var(--coral)";
    }
    if (envMode) envMode.textContent = envLabel;

    const aboutUptime = document.getElementById("about-backend-uptime");
    const aboutYolo = document.getElementById("about-yolo-model");
    const aboutFile = document.getElementById("about-model-file");
    const aboutFw = document.getElementById("about-sensor-fw");
    if (aboutUptime) aboutUptime.textContent = backendOk ? fmtUptime(uptimeSec) : "Offline";
    if (aboutYolo) aboutYolo.textContent = yoloVersion;
    if (aboutFile) aboutFile.textContent = modelFile;
    if (aboutFw) aboutFw.textContent = sensorFw;
  }

  function applySettings() {
    const s = settings;
    document.body.classList.toggle("pv-compact", Boolean(s.compactMode));
    document.body.classList.toggle("pv-reduced-motion", !s.animations);
    const particles = document.getElementById("particles");
    if (particles) particles.style.display = s.particles ? "" : "none";

    const hud = document.querySelector(".scanner-hud");
    if (hud) hud.classList.toggle("hud-hidden", !s.hudOverlay);
    const camHud = document.getElementById("cam-hud");
    if (camHud) camHud.classList.toggle("hud-hidden", !s.hudOverlay);

    bindFormFromSettings();
    updateStorageEstimate();
    syncIdentityFields();
  }

  function syncIdentityFields() {
    const apiEl = document.getElementById("set-api-url");
    if (apiEl) apiEl.textContent = window.PLANT_API_BASE || "—";
    const uid = document.getElementById("set-user-id");
    const zid = document.getElementById("set-zone-id");
    const did = document.getElementById("set-device-id");
    if (uid && document.activeElement !== uid) uid.value = window.PLANT_USER_ID || "";
    if (zid && document.activeElement !== zid) zid.value = window.PLANT_ZONE_ID || "";
    if (did && document.activeElement !== did) did.value = window.PLANT_DEVICE_ID || "";
  }

  function updateStorageEstimate() {
    const el = document.getElementById("set-storage-size");
    if (!el) return;
    let bytes = 0;
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i);
      bytes += (k ? k.length : 0) + (localStorage.getItem(k) || "").length;
    }
    const kb = (bytes / 1024).toFixed(1);
    el.textContent = kb + " KB";
  }

  function bindFormFromSettings() {
    const s = settings;
    const setChk = (id, v) => {
      const el = document.getElementById(id);
      if (el) el.checked = Boolean(v);
    };
    const setVal = (id, v) => {
      const el = document.getElementById(id);
      if (el && el.value !== String(v)) el.value = String(v);
    };
    const setLbl = (id, t) => {
      const el = document.getElementById(id);
      if (el) el.textContent = t;
    };

    setChk("set-autoscan", s.autoScan);
    setChk("set-hud", s.hudOverlay);
    setChk("set-sound", s.soundEffects);
    setChk("set-multiangle", s.multiAngle);
    setChk("set-notif", s.notifications);
    setChk("set-anim", s.animations);
    setChk("set-particles", s.particles);
    setChk("set-compact", s.compactMode);
    setChk("set-autocalib", s.autoCalibrate);

    const conf = document.getElementById("set-conf-threshold");
    if (conf) conf.value = s.confidenceThreshold;
    setLbl("set-conf-val", s.confidenceThreshold + "%");

    setVal("set-resolution", s.resolution);
    setVal("set-flash", s.flashMode);
    setVal("set-poll-interval", s.sensorPollSec);

    const temp = document.getElementById("set-temp-alert");
    if (temp) temp.value = s.tempAlertC;
    setLbl("set-temp-val", s.tempAlertC + "°C");

    const hum = document.getElementById("set-hum-low");
    if (hum) hum.value = s.humidityAlertLow;
    setLbl("set-hum-low-val", s.humidityAlertLow + "%");

    const soil = document.getElementById("set-soil-alert");
    if (soil) soil.value = s.soilMoistureAlertLow;
    setLbl("set-soil-val", s.soilMoistureAlertLow + "%");

    const phMin = document.getElementById("set-ph-min");
    const phMax = document.getElementById("set-ph-max");
    if (phMin) phMin.value = s.phMin;
    if (phMax) phMax.value = s.phMax;
    syncPhRange(null);

    const ec = document.getElementById("set-ec-alert");
    if (ec) ec.value = s.ecAlertHigh;
    setLbl("set-ec-val", s.ecAlertHigh.toFixed(1));
  }

  function syncPhRange(activeId, save) {
    const minEl = document.getElementById("set-ph-min");
    const maxEl = document.getElementById("set-ph-max");
    if (!minEl || !maxEl) return { lo: 5.5, hi: 7.5 };

    let lo = parseFloat(minEl.value);
    let hi = parseFloat(maxEl.value);
    if (Number.isNaN(lo)) lo = PH_ABS_MIN;
    if (Number.isNaN(hi)) hi = PH_ABS_MAX;

    if (hi - lo < PH_MIN_GAP) {
      if (activeId === "set-ph-min") {
        lo = Math.max(PH_ABS_MIN, hi - PH_MIN_GAP);
        minEl.value = lo.toFixed(1);
      } else {
        hi = Math.min(PH_ABS_MAX, lo + PH_MIN_GAP);
        maxEl.value = hi.toFixed(1);
      }
    }

    lo = Math.max(PH_ABS_MIN, Math.min(lo, PH_ABS_MAX - PH_MIN_GAP));
    hi = Math.min(PH_ABS_MAX, Math.max(hi, PH_ABS_MIN + PH_MIN_GAP));
    if (hi - lo < PH_MIN_GAP) {
      if (activeId === "set-ph-max") hi = Math.min(PH_ABS_MAX, lo + PH_MIN_GAP);
      else lo = Math.max(PH_ABS_MIN, hi - PH_MIN_GAP);
      minEl.value = lo.toFixed(1);
      maxEl.value = hi.toFixed(1);
    }

    const maxAllowedForMin = parseFloat((hi - PH_MIN_GAP).toFixed(1));
    const minAllowedForMax = parseFloat((lo + PH_MIN_GAP).toFixed(1));
    minEl.max = String(maxAllowedForMin);
    maxEl.min = String(minAllowedForMax);

    const fill = document.getElementById("set-ph-fill");
    if (fill) {
      const span = PH_ABS_MAX - PH_ABS_MIN;
      const leftPct = ((lo - PH_ABS_MIN) / span) * 100;
      const widthPct = ((hi - lo) / span) * 100;
      fill.style.left = leftPct + "%";
      fill.style.width = widthPct + "%";
    }

    const lbl = document.getElementById("set-ph-val");
    if (lbl) lbl.textContent = lo.toFixed(1) + "–" + hi.toFixed(1);

    if (save) saveSettings({ phMin: lo, phMax: hi }, "pH range updated");
    return { lo, hi };
  }

  function wireControls() {
    const rangeBind = (id, lblId, fmt, key, toastMsg, parser) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.addEventListener("input", () => {
        const lbl = document.getElementById(lblId);
        if (lbl) lbl.textContent = fmt(el);
      });
      el.addEventListener("change", () => {
        const patch = {};
        patch[key] = parser(el);
        saveSettings(patch, toastMsg);
      });
    };
    rangeBind("set-conf-threshold", "set-conf-val", (el) => parseInt(el.value, 10) + "%", "confidenceThreshold", "Threshold updated", (el) => parseInt(el.value, 10));
    rangeBind("set-temp-alert", "set-temp-val", (el) => parseInt(el.value, 10) + "°C", "tempAlertC", "Temperature alert updated", (el) => parseInt(el.value, 10));
    rangeBind("set-hum-low", "set-hum-low-val", (el) => parseInt(el.value, 10) + "%", "humidityAlertLow", "Humidity alert updated", (el) => parseInt(el.value, 10));
    rangeBind("set-soil-alert", "set-soil-val", (el) => parseInt(el.value, 10) + "%", "soilMoistureAlertLow", "Moisture alert updated", (el) => parseInt(el.value, 10));
    rangeBind("set-ec-alert", "set-ec-val", (el) => parseFloat(el.value).toFixed(1), "ecAlertHigh", "EC threshold updated", (el) => parseFloat(el.value));

    const toggles = [
      ["set-autoscan", "autoScan", "Auto scan preference saved"],
      ["set-hud", "hudOverlay", null],
      ["set-sound", "soundEffects", null],
      ["set-multiangle", "multiAngle", "Multi-angle preference saved"],
      ["set-notif", "notifications", "Notifications updated"],
      ["set-anim", "animations", "Animations updated"],
      ["set-particles", "particles", "Particle background updated"],
      ["set-compact", "compactMode", "Compact mode updated"],
      ["set-autocalib", "autoCalibrate", "Calibration preference saved"],
    ];
    toggles.forEach(([id, key, msg]) => {
      document.getElementById(id)?.addEventListener("change", (e) => {
        const patch = {};
        patch[key] = e.target.checked;
        let toast = msg;
        if (key === "hudOverlay") toast = e.target.checked ? "Camera overlay enabled" : "Camera overlay disabled";
        if (key === "soundEffects") toast = e.target.checked ? "Sound enabled" : "Sound disabled";
        saveSettings(patch, toast);
      });
    });

    document.getElementById("set-resolution")?.addEventListener("change", (e) => {
      saveSettings({ resolution: parseInt(e.target.value, 10) }, "Resolution updated");
    });
    document.getElementById("set-flash")?.addEventListener("change", (e) => {
      saveSettings({ flashMode: e.target.value }, "Flash mode updated");
    });
    document.getElementById("set-poll-interval")?.addEventListener("change", (e) => {
      saveSettings({ sensorPollSec: parseInt(e.target.value, 10) }, "Sensor polling updated");
    });

    const phMinEl = document.getElementById("set-ph-min");
    const phMaxEl = document.getElementById("set-ph-max");
    const phOnInput = (id) => () => syncPhRange(id, false);
    const phOnChange = (id) => () => syncPhRange(id, true);
    phMinEl?.addEventListener("input", phOnInput("set-ph-min"));
    phMaxEl?.addEventListener("input", phOnInput("set-ph-max"));
    phMinEl?.addEventListener("change", phOnChange("set-ph-min"));
    phMaxEl?.addEventListener("change", phOnChange("set-ph-max"));

    const persistIdentity = (key, storageKey, windowKey) => {
      return (e) => {
        const v = (e.target.value || "").trim();
        if (!v) return;
        localStorage.setItem(storageKey, v);
        window[windowKey] = v;
        showToast("Session identity updated");
        syncIdentityFields();
      };
    };
    document.getElementById("set-user-id")?.addEventListener("change", persistIdentity("user", "pv-user-id", "PLANT_USER_ID"));
    document.getElementById("set-zone-id")?.addEventListener("change", persistIdentity("zone", "pv-zone-id", "PLANT_ZONE_ID"));
    document.getElementById("set-device-id")?.addEventListener("change", persistIdentity("device", "pv-device-id", "PLANT_DEVICE_ID"));

    document.getElementById("btn-sensor-reconnect")?.addEventListener("click", async () => {
      showToast("Reconnecting sensor…");
      if (typeof window.plantSensorRefresh === "function") {
        await window.plantSensorRefresh(true);
      }
      await refreshSystemStatus();
      showToast("Sensor poll complete");
    });

    document.getElementById("btn-clear")?.addEventListener("click", () => {
      if (!confirm("Clear cached zones, notifications, and profile data? Scanner settings are kept.")) return;
      ["pv-zones", "pv-notifications", "pv-notif-counter", "pv-profile", "pv-chat-pos"].forEach((k) =>
        localStorage.removeItem(k)
      );
      updateStorageEstimate();
      showToast("Cached app data cleared");
    });

    // -----------------------------------------------------------------
    // Phase 4 (A3): Demo Mode toggle wiring.
    // The state lives in `localStorage.PLANT_DEMO_MODE` and is owned by
    // `window.plantDemo` (see demo_fixtures.js). We only mirror it into
    // the checkbox + topbar chip here so the settings UI stays in sync.
    // -----------------------------------------------------------------
    const demoBox = document.getElementById("set-demo-mode");
    if (demoBox && window.plantDemo) {
      demoBox.checked = window.plantDemo.isOn();
      _renderDemoChip();
      _renderDemoState();
      demoBox.addEventListener("change", (e) => {
        const on = !!e.target.checked;
        window.plantDemo.setOn(on);
        _renderDemoChip();
        _renderDemoState();
        showToast(on ? "Demo Mode enabled — using fixtures" : "Demo Mode disabled — using live backend");
      });
    }
    window.addEventListener("plantvision:demo-mode-changed", () => {
      const b = document.getElementById("set-demo-mode");
      if (b && window.plantDemo) b.checked = window.plantDemo.isOn();
      _renderDemoChip();
      _renderDemoState();
    });

    // Phase Final — scenario dropdown (healthy vs warning).
    const scenSel = document.getElementById("set-demo-scenario");
    if (scenSel && window.plantDemo && typeof window.plantDemo.setScenario === "function") {
      try { scenSel.value = window.plantDemo.scenario(); } catch (_) {}
      scenSel.addEventListener("change", (e) => {
        const v = window.plantDemo.setScenario(e.target.value);
        showToast("Demo scenario: " + (v === "healthy" ? "Thriving cucumber" : "Powdery mildew (warning)"));
      });
    }

    // -----------------------------------------------------------------
    // Phase 4 (B2): wire the Devices diagnostics refresh on the
    // Settings page. We refresh on page-show + every 10s while the
    // page is visible.
    // -----------------------------------------------------------------
    _ensureDevicesDiagnosticsPoll();
  }

  function _renderDemoChip() {
    const chip = document.getElementById("sys-chip-demo");
    if (!chip) return;
    const on = !!(window.plantDemo && window.plantDemo.isOn());
    chip.hidden = !on;
    chip.title = on
      ? "Demo Mode is active — backend, ESP32 and Supabase are bypassed. Toggle in Settings → Demo Mode."
      : "Demo Mode is off";
  }
  function _renderDemoState() {
    const t = document.getElementById("set-demo-state");
    if (!t) return;
    const on = !!(window.plantDemo && window.plantDemo.isOn());
    t.textContent = on ? "On · using fixtures" : "Off · live backend";
    t.style.color = on ? "var(--gold)" : "var(--sage)";
  }

  // -----------------------------------------------------------------
  // Phase 4 (B2): Devices diagnostics table
  // -----------------------------------------------------------------
  let _devTimer = null;
  function _ensureDevicesDiagnosticsPoll() {
    _refreshDevicesDiagnostics();
    if (_devTimer) clearInterval(_devTimer);
    _devTimer = setInterval(_refreshDevicesDiagnostics, 10000);
  }

  function _fmtAgeSec(sec) {
    if (sec == null || Number.isNaN(sec)) return "—";
    if (sec < 60) return Math.round(sec) + "s";
    if (sec < 3600) return Math.round(sec / 60) + "m";
    if (sec < 86400) return Math.round(sec / 3600) + "h";
    return Math.round(sec / 86400) + "d";
  }

  function _escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function _refreshDevicesDiagnostics() {
    const host = document.getElementById("set-devices-table");
    const counter = document.getElementById("set-devices-count");
    if (!host) return;

    let payload = null;
    try {
      if (typeof fetchDeviceDiagnostics === "function") {
        payload = await fetchDeviceDiagnostics();
      }
    } catch (_) { /* swallowed below */ }

    if (!payload || !Array.isArray(payload.devices)) {
      if (counter) counter.textContent = "—";
      host.innerHTML = '<div class="set-devices-empty mono">No diagnostics available (backend offline?).</div>';
      return;
    }

    const devs = payload.devices;
    if (counter) counter.textContent = devs.length + (devs.length === 1 ? " device" : " devices");

    if (!devs.length) {
      host.innerHTML = '<div class="set-devices-empty mono">No devices registered yet. Send a /sensor reading or call /devices/register.</div>';
      return;
    }

    const head = '<div class="set-dev-row set-dev-head">'
      + '<span>Slug</span><span>Zone</span><span>Freshness</span>'
      + '<span>Last seen</span><span>Retries</span><span>Reach</span>'
      + '</div>';
    const rows = devs.map((d) => {
      const fresh = d.freshness || "offline";
      const cls = fresh === "live" ? "fresh-live" : fresh === "stale" ? "fresh-stale" : "fresh-off";
      const reach = d.reachable === false ? "no" : "yes";
      const retries = (d.retry_counters && (d.retry_counters.failed || 0)) || 0;
      const age = (d.age_seconds != null) ? _fmtAgeSec(d.age_seconds) : "—";
      return `<div class="set-dev-row ${cls}">`
        + `<span class="mono">${_escapeHtml(d.slug)}</span>`
        + `<span>${_escapeHtml(d.zone_id || "—")}</span>`
        + `<span class="set-dev-fresh">${_escapeHtml(fresh)}</span>`
        + `<span class="mono">${age}</span>`
        + `<span class="mono">${retries}</span>`
        + `<span class="mono">${reach}</span>`
        + `</div>`;
    }).join("");
    host.innerHTML = head + rows;
  }

  function startStatusPolling() {
    if (statusTimer) return;
    refreshSystemStatus();
    statusTimer = setInterval(refreshSystemStatus, POLL_MS);
  }

  function stopStatusPolling() {
    if (statusTimer) {
      clearInterval(statusTimer);
      statusTimer = null;
    }
  }

  function onNavigate(targetId) {
    if (targetId === "page-settings") {
      applySettings();
      syncIdentityFields();
      refreshSystemStatus();
      startStatusPolling();
    } else {
      stopStatusPolling();
    }
  }

  function recordScanComplete() {
    lastScanTs = Math.floor(Date.now() / 1000);
    localStorage.setItem("pv-last-scan-ts", String(lastScanTs));
  }

  function playScanSound() {
    if (!settings.soundEffects) return;
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = 880;
      gain.gain.value = 0.06;
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + 0.12);
    } catch (_) {
      /* optional */
    }
  }

  function getCameraConstraints() {
    const res = settings.resolution || 1080;
    return {
      video: {
        facingMode: { ideal: "environment" },
        width: { ideal: res },
        height: { ideal: Math.round(res * 0.75) },
      },
      audio: false,
    };
  }

  async function applyTorchIfNeeded(stream) {
    if (!stream || settings.flashMode === "off") return;
    const track = stream.getVideoTracks()[0];
    if (!track) return;
    try {
      const caps = track.getCapabilities?.();
      if (caps && "torch" in caps) {
        await track.applyConstraints({
          advanced: [{ torch: settings.flashMode === "on" }],
        });
      }
    } catch (_) {
      /* torch not supported */
    }
  }

  function meetsConfidenceThreshold(confidence) {
    return (confidence ?? 0) * 100 >= (settings.confidenceThreshold || 85);
  }

  window.plantVisionSettings = {
    get: getSettings,
    save: saveSettings,
    showToast,
    onNavigate,
    recordScanComplete,
    playScanSound,
    getCameraConstraints,
    applyTorchIfNeeded,
    meetsConfidenceThreshold,
    refreshStatus: refreshSystemStatus,
  };

  wireControls();
  applySettings();
  startStatusPolling();

  // Phase 4 (A3): ensure the topbar DEMO chip reflects state on every
  // page load, not only after the user visits Settings.
  _renderDemoChip();

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      applySettings();
      _renderDemoChip();
    });
  }
})();
