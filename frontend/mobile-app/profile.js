/**
 * Operator Profile — live MVP session dashboard.
 */
(function () {
  const POLL_MS = 8000;
  let pollTimer = null;

  const ZONE_LABELS = {
    zone_alpha: "Zone Alpha",
    zone_beta: "Zone Beta",
    zone_gamma: "Zone Gamma",
    zone_delta: "Zone Delta",
  };

  function $(id) {
    return document.getElementById(id);
  }

  function zoneLabel(zid) {
    return ZONE_LABELS[zid] || (zid || "—").replace(/_/g, " ");
  }

  function fmtAgo(ts) {
    if (!ts) return "never";
    const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (sec < 60) return sec + "s ago";
    if (sec < 3600) return Math.floor(sec / 60) + "m ago";
    return Math.floor(sec / 3600) + "h ago";
  }

  function fmtTime(ts) {
    if (!ts) return "—";
    return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function sessionMode(summary, backendOk) {
    if (!backendOk) return { label: "Offline", cls: "off" };
    if (summary && summary.source === "demo") return { label: "Simulation", cls: "sim" };
    if (summary && summary.total_scans > 0) return { label: "Live", cls: "live" };
    return { label: "Local Session", cls: "local" };
  }

  function setRing(pct) {
    const ring = $("prof-health-ring");
    const val = $("prof-health-val");
    if (!ring || !val) return;
    const p = Math.max(0, Math.min(100, pct || 0));
    val.textContent = p + "%";
    const circ = 2 * Math.PI * 52;
    const offset = circ * (1 - p / 100);
    ring.style.strokeDasharray = circ.toFixed(2);
    ring.style.strokeDashoffset = offset.toFixed(2);
    ring.classList.remove("phr-warn", "phr-crit", "phr-ok");
    if (p >= 75) ring.classList.add("phr-ok");
    else if (p >= 50) ring.classList.add("phr-warn");
    else ring.classList.add("phr-crit");
  }

  function setDiag(key, state, label) {
    const dot = $("prof-diag-" + key);
    const lbl = $("prof-diag-lbl-" + key);
    if (dot) dot.className = "prof-diag-dot pd-" + state;
    if (lbl) lbl.textContent = label;
  }

  function bindIdentityFields() {
    const uid = $("prof-session-user");
    const zid = $("prof-session-zone");
    const did = $("prof-session-device");
    if (uid) {
      uid.value = window.PLANT_USER_ID || "demo_user";
      uid.addEventListener("change", () => {
        window.PLANT_USER_ID = uid.value.trim() || "demo_user";
        localStorage.setItem("pv-user-id", window.PLANT_USER_ID);
        refresh(true);
      });
    }
    if (zid) {
      zid.value = window.PLANT_ZONE_ID || "zone_alpha";
      zid.addEventListener("change", () => {
        window.PLANT_ZONE_ID = zid.value.trim() || "zone_alpha";
        localStorage.setItem("pv-zone-id", window.PLANT_ZONE_ID);
        refresh(true);
      });
    }
    if (did) {
      did.value = window.PLANT_DEVICE_ID || "esp32_001";
      did.addEventListener("change", () => {
        window.PLANT_DEVICE_ID = did.value.trim() || "esp32_001";
        localStorage.setItem("pv-device-id", window.PLANT_DEVICE_ID);
        refresh(true);
      });
    }
  }

  function syncPreferenceToggles() {
    const s =
      window.plantVisionSettings && typeof window.plantVisionSettings.get === "function"
        ? window.plantVisionSettings.get()
        : null;
    if (!s) return;
    const map = {
      "prof-pref-notif": s.notifications,
      "prof-pref-anim": s.animations,
      "prof-pref-sound": s.soundEffects,
      "prof-pref-particles": s.particles,
      "prof-pref-compact": s.compactMode,
      "prof-pref-hud": s.hudOverlay,
      "prof-pref-autoscan": s.autoScan,
    };
    Object.entries(map).forEach(([id, val]) => {
      const el = $(id);
      if (el) el.checked = !!val;
    });
    const res = $("prof-pref-resolution");
    if (res) res.value = String(s.resolution || 1080);
    const flash = $("prof-pref-flash");
    if (flash) flash.value = s.flashMode || "auto";
  }

  function wirePreferenceToggles() {
    document.querySelectorAll("[data-prof-setting]").forEach((el) => {
      el.addEventListener("change", () => {
        const key = el.getAttribute("data-prof-setting");
        if (!key || !window.plantVisionSettings) return;
        const partial = {};
        if (key === "resolution") partial.resolution = parseInt(el.value, 10) || 1080;
        else if (key === "flashMode") partial.flashMode = el.value;
        else partial[key] = el.type === "checkbox" ? el.checked : el.value;
        window.plantVisionSettings.save(partial);
      });
    });
  }

  let _prevScans = null;

  function animateCounter(el, target) {
    if (!el) return;
    const end = parseFloat(String(target).replace(/[^0-9.]/g, "")) || 0;
    const start = parseFloat(el.dataset.val || "0") || 0;
    if (Math.abs(end - start) < 0.01) {
      el.textContent = target;
      el.dataset.val = String(end);
      return;
    }
    const t0 = performance.now();
    function tick(now) {
      const p = Math.min(1, (now - t0) / 520);
      const v = start + (end - start) * (1 - Math.pow(1 - p, 3));
      el.textContent = String(Math.round(v));
      if (p < 1) requestAnimationFrame(tick);
      else {
        el.textContent = target;
        el.dataset.val = String(end);
      }
    }
    requestAnimationFrame(tick);
  }

  function setTrend(id, text, cls) {
    const el = $(id);
    if (!el) return;
    el.textContent = text || "";
    el.className = "prof-metric-trend" + (cls ? " " + cls : "");
  }
  function renderMetrics(summary, health, history) {
    const scans = summary ? summary.total_scans : 0;
    const conf = summary ? ((summary.avg_confidence || 0) * 100).toFixed(1) + "%" : "—";
    const scansEl = $("prof-metric-scans");
    if (scansEl) animateCounter(scansEl, String(scans));
    const confEl = $("prof-metric-conf");
    if (confEl) confEl.textContent = conf;
    const zonesEl = $("prof-metric-zones");
    if (zonesEl) zonesEl.textContent = summary ? String(summary.active_zones) : "—";
    const devEl = $("prof-metric-devices");
    if (devEl) devEl.textContent = summary ? String(summary.connected_devices) : "—";
    const last = history && history[0];
    const disEl = $("prof-metric-disease");
    if (disEl) disEl.textContent = last ? last.disease : health ? health.class_name || "—" : "—";
    if (_prevScans !== null && scans > _prevScans) {
      setTrend("prof-trend-scans", "↑ +" + (scans - _prevScans) + " scans", "up");
    } else if (scans > 0) {
      setTrend("prof-trend-scans", "● session active", "live");
    }
    _prevScans = scans;
    if (summary && summary.avg_confidence < 0.55) {
      setTrend("prof-trend-conf", "↓ confidence drift", "warn");
    } else if (summary && summary.avg_confidence >= 0.7) {
      setTrend("prof-trend-conf", "↑ stable reads", "up");
    }
    setTrend("prof-trend-zones", summary ? summary.active_zones + " monitored" : "", "");
    const devTrend = $("prof-trend-devices");
    if (devTrend && summary && summary.connected_devices > 0) {
      devTrend.textContent = "● live sensor active";
    }
  }
  function renderAiSummary(scan, health, sensor) {
    const scanEl = $("prof-ai-scan");
    const zoneEl = $("prof-ai-zone");
    const envEl = $("prof-ai-env");
    const recEl = $("prof-ai-rec");
    const chips = $("prof-ai-chips");
    const body = $("prof-ai-body");
    const empty = $("prof-ai-empty");
    const timeEl = $("prof-ai-time");
    const tag = $("prof-ai-tag");
    const zid = window.PLANT_ZONE_ID || "zone_alpha";
    const hasData = !!(scan || health);

    if (body) body.hidden = !hasData;
    if (empty) empty.hidden = hasData;
    if (tag) tag.textContent = scan ? "● Live" : health ? "◆ Ready" : "○ Idle";

    if (chips) {
      const hPct = health ? health.plant_health : null;
      const hCls = hPct >= 75 ? "prof-ai-chip-health" : hPct >= 50 ? "prof-ai-chip-env" : "prof-ai-chip-trend";
      chips.innerHTML = [
        health ? `<span class="prof-ai-chip ${hCls}">Health ${hPct}%</span>` : "",
        sensor ? `<span class="prof-ai-chip prof-ai-chip-env">Env live</span>` : `<span class="prof-ai-chip prof-ai-chip-trend">Awaiting sensor</span>`,
        scan ? `<span class="prof-ai-chip prof-ai-chip-trend">Scan ${((scan.confidence || 0) * 100).toFixed(0)}%</span>` : "",
      ].filter(Boolean).join("");
    }

    if (scanEl) {
      scanEl.textContent = scan
        ? `${scan.disease} (${((scan.confidence || 0) * 100).toFixed(1)}%)`
        : "No scan in session yet";
    }
    if (zoneEl) zoneEl.textContent = zoneLabel(scan?.zone_id || zid);
    if (envEl) {
      if (sensor) {
        envEl.textContent = `Air ${sensor.air_humidity}% RH · soil ${sensor.soil_humidity}% · ${sensor.air_temperature}°C`;
      } else if (health) {
        envEl.textContent = `Environment stress: ${health.environment_stress}`;
      } else {
        envEl.textContent = "Awaiting live sensor stream";
      }
    }
    if (recEl) {
      recEl.textContent =
        health?.recommendation || "Run a scan to generate AI recommendations.";
    }
    if (timeEl) {
      const ts = localStorage.getItem("pv-last-scan-ts");
      timeEl.textContent = ts ? "Last activity · " + fmtAgo(parseInt(ts, 10)) : "Monitoring active";
    }
  }
  function renderHealthBreakdown(health) {
    if (!health) {
      setRing(0);
      ["risk", "stress", "survival"].forEach((k) => {
        const el = $("prof-h-" + k);
        if (el) el.textContent = "—";
      });
      return;
    }
    setRing(health.plant_health);
    const risk = $("prof-h-risk");
    const stress = $("prof-h-stress");
    const surv = $("prof-h-survival");
    if (risk) risk.textContent = health.disease_risk;
    if (stress) stress.textContent = health.environment_stress;
    if (surv) surv.textContent = health.survival_chance + "%";
  }

  function renderEvents(events) {
    const list = $("prof-activity-list");
    if (!list) return;
    if (!events || !events.length) {
      list.innerHTML =
        '<div class="prof-act-empty prof-act-empty-premium"><div class="garden-empty-pulse"><span class="garden-empty-icon">◎</span></div><strong>Monitoring active</strong><span>Waiting for scan or sensor events…</span></div>';
      return;
    }
    const typeIcon = { scan: "🔬", sensor: "📡", alert: "⚠", ai: "✦", device: "◉", system: "◇" };
    list.innerHTML = events
      .slice(0, 12)
      .map((e) => {
        const ico = typeIcon[e.event_type] || "•";
        const sev =
          e.event_type === "alert"
            ? "alert"
            : e.event_type === "scan"
              ? "scan"
              : e.event_type === "ai"
                ? "ai"
                : "sys";
        return `<div class="prof-act-item prof-act-${sev}"><span class="prof-act-ico">${ico}</span><div><span class="prof-act-text">${e.message}</span><span class="prof-act-time mono">${fmtAgo(e.timestamp)}</span></div></div>`;
      })
      .join("");
  }

  async function refreshDiagnostics() {
    let backendOk = false;
    let uptime = "—";
    if (typeof checkBackendHealth === "function") {
      const h = await checkBackendHealth();
      backendOk = h.ok;
      if (h.ok && h.data) uptime = (h.data.uptime_sec || 0) + "s uptime";
    }
    setDiag("api", backendOk ? "ok" : "off", backendOk ? "Online" : "Offline");

    let yoloState = "warn";
    let yoloLbl = "Unknown";
    if (typeof fetchModelsHealth === "function") {
      const mh = await fetchModelsHealth();
      if (mh.ok && mh.data) {
        const loaded = mh.data.yolo_loaded || mh.data.vision_loaded;
        yoloState = loaded ? "ok" : "warn";
        yoloLbl = loaded ? "Loaded" : "Stub / demo";
      }
    }
    setDiag("yolo", yoloState, yoloLbl);
    setDiag("analytics", backendOk ? "ok" : "off", backendOk ? "Active" : "Offline");

    const cam = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia);
    setDiag("camera", cam ? "ok" : "warn", cam ? "Available" : "Limited");

    let sensorLbl = "No feed";
    let sensorSt = "warn";
    try {
      if (typeof fetchSensorLatest === "function") {
        const res = await fetchSensorLatest();
        if (res && res.reading) {
          sensorSt = res.source === "live" ? "ok" : "sim";
          sensorLbl = res.source === "live" ? "Live" : "Demo stream";
          const ts = $("prof-metric-sensor-ts");
          if (ts) ts.textContent = fmtAgo(_parseTs(res.reading.timestamp));
        }
      }
    } catch (_) {
      sensorSt = "off";
      sensorLbl = "Offline";
    }
    setDiag("sensor", sensorSt, sensorLbl);
    setDiag("health", backendOk ? "ok" : "off", backendOk ? "Active" : "Offline");

    const rt = $("prof-runtime-uptime");
    if (rt) rt.textContent = uptime;
    const camPerm = $("prof-runtime-camera");
    if (camPerm) camPerm.textContent = cam ? "Granted / available" : "Not available";
  }

  function _parseTs(iso) {
    try {
      return new Date(iso.replace("Z", "+00:00")).getTime() / 1000;
    } catch (_) {
      return 0;
    }
  }

  async function refresh(force) {
    const tag = $("prof-live-tag");
    const polled = $("prof-polled-at");
    const modeEl = $("prof-session-mode");

    let summary = null;
    let events = null;
    let health = null;
    let history = null;
    let sensor = null;
    let backendOk = false;

    if (typeof checkBackendHealth === "function") {
      const h = await checkBackendHealth();
      backendOk = h.ok;
    }

    try {
      [summary, events, health, history] = await Promise.all([
        fetchAnalyticsSummary(),
        fetchAnalyticsEvents(15),
        typeof fetchPlantHealth === "function" ? fetchPlantHealth() : null,
        fetchAnalyticsHistory(3),
      ]);
    } catch (_) {}

    try {
      const sr = await fetchSensorLatest();
      sensor = sr?.reading || null;
    } catch (_) {}

    const lastScan =
      window.plantAssistant && window.plantAssistant.getContext
        ? window.plantAssistant.getContext().lastScan
        : null;
    const scanForAi =
      lastScan ||
      (history && history[0]
        ? {
            disease: history[0].disease,
            confidence: history[0].confidence,
            zone_id: history[0].zone_id,
          }
        : null);

    const mode = sessionMode(summary, backendOk);
    if (modeEl) {
      modeEl.textContent = mode.label;
      modeEl.className = "prof-session-badge psb-" + mode.cls;
    }
    if (tag) {
      tag.textContent = mode.cls === "live" ? "● Live" : mode.cls === "sim" ? "◆ Simulation" : "○ " + mode.label;
    }
    if (polled) polled.textContent = "Updated " + fmtTime(Math.floor(Date.now() / 1000));

    $("prof-display-user") &&
      ($("prof-display-user").textContent = window.PLANT_USER_ID || "demo_user");
    $("prof-display-zone") &&
      ($("prof-display-zone").textContent = zoneLabel(window.PLANT_ZONE_ID));
    $("prof-display-device") &&
      ($("prof-display-device").textContent = window.PLANT_DEVICE_ID || "esp32_001");

    const lastActive = $("prof-last-active");
    if (lastActive) {
      const ts = localStorage.getItem("pv-last-scan-ts");
      lastActive.textContent = ts ? "Last active " + fmtAgo(parseInt(ts, 10)) : "Session active now";
    }

    renderHealthBreakdown(health);
    renderAiSummary(scanForAi, health, sensor);
    renderMetrics(summary, health, history);
    renderEvents(events);
    await refreshDiagnostics();

    const apiUrl = $("prof-runtime-api");
    if (apiUrl) apiUrl.textContent = window.PLANT_API_BASE || "—";
    const model = $("prof-runtime-model");
    if (model && typeof fetchModelsRegistry === "function") {
      const reg = await fetchModelsRegistry();
      if (reg.ok && reg.data) model.textContent = reg.data.vision?.weights_path || reg.data.yolo?.path || "—";
    }
    const lastScanEl = $("prof-runtime-lastscan");
    if (lastScanEl) {
      const ts = localStorage.getItem("pv-last-scan-ts");
      lastScanEl.textContent = ts ? fmtAgo(parseInt(ts, 10)) : "—";
    }
    const analyticsMode = $("prof-runtime-analytics");
    if (analyticsMode) analyticsMode.textContent = summary?.source === "demo" ? "Simulation" : "Live";

    if (force && window.plantAssistant) window.plantAssistant.refreshContext();
  }

  function exportSession() {
    const data = {
      exportedAt: new Date().toISOString(),
      user_id: window.PLANT_USER_ID,
      zone_id: window.PLANT_ZONE_ID,
      device_id: window.PLANT_DEVICE_ID,
      api_base: window.PLANT_API_BASE,
      settings:
        window.plantVisionSettings && window.plantVisionSettings.get
          ? window.plantVisionSettings.get()
          : null,
      zones: JSON.parse(localStorage.getItem("pv-zones") || "[]"),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "plantvision-session-export.json";
    a.click();
    URL.revokeObjectURL(url);
  }

  function clearLocalCache() {
    if (!confirm("Clear local cache (zones, notifications, chat position)? Settings and API identity are kept.")) return;
    ["pv-zones", "pv-notifications", "pv-notif-counter", "pv-chat-pos", "pv-profile"].forEach((k) =>
      localStorage.removeItem(k)
    );
    if (window.plantVisionSettings && window.plantVisionSettings.showToast) {
      window.plantVisionSettings.showToast("Local cache cleared");
    }
    refresh(true);
  }

  function resetDemoSession() {
    if (!confirm("Reset demo session IDs to defaults?")) return;
    window.PLANT_USER_ID = "demo_user";
    window.PLANT_ZONE_ID = "zone_alpha";
    window.PLANT_DEVICE_ID = "esp32_001";
    localStorage.setItem("pv-user-id", "demo_user");
    localStorage.setItem("pv-zone-id", "zone_alpha");
    localStorage.setItem("pv-device-id", "esp32_001");
    bindIdentityFields();
    refresh(true);
  }

  function onNavigate(targetId) {
    if (targetId === "page-profile") {
      refresh(true);
      if (!pollTimer) pollTimer = setInterval(() => refresh(false), POLL_MS);
    }
  }

  function init() {
    bindIdentityFields();
    syncPreferenceToggles();
    wirePreferenceToggles();
    $("prof-export-session")?.addEventListener("click", exportSession);
    $("prof-clear-cache")?.addEventListener("click", clearLocalCache);
    $("prof-reset-demo")?.addEventListener("click", resetDemoSession);
    $("prof-goto-settings")?.addEventListener("click", () => {
      if (typeof switchPage === "function") switchPage("page-settings");
    });
    window.addEventListener("plantvision:settings-changed", syncPreferenceToggles);
  }

  window.plantProfile = { refresh, onNavigate };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
