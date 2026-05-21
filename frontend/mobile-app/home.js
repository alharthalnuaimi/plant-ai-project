/**
 * PlantVision Home — premium live dashboard.
 *
 * Drives status cards, simulation/live mode badge, scanner-footer pulse,
 * and scan-log header pulse from analytics + garden dashboards. Pure UI:
 * never mutates backend state or API contracts.
 */
(function () {
  const POLL_MS = 6000;
  let pollTimer = null;
  let lastModeKey = "";
  let lastStatsKey = "";
  let lastPulseKey = "";
  let lastFootKey = "";

  function $(id) {
    return document.getElementById(id);
  }

  function fmtAgo(ts) {
    if (!ts) return "—";
    const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (sec < 60) return sec + "s ago";
    if (sec < 3600) return Math.floor(sec / 60) + "m ago";
    if (sec < 86400) return Math.floor(sec / 3600) + "h ago";
    return Math.floor(sec / 86400) + "d ago";
  }

  function statusToTag(s) {
    if (s === "PASS" || s === "HEALTHY") return "et-ok";
    if (s === "WARN" || s === "WARNING") return "et-warn";
    if (s === "CRITICAL" || s === "FAIL") return "et-crit";
    return "et-warn";
  }

  function safeNum(v) {
    return typeof v === "number" && !Number.isNaN(v) ? v : 0;
  }

  function setMode(isLive, sensorCtx) {
    const badge = $("home-mode-badge");
    if (!badge) return;
    const stale = sensorCtx && sensorCtx.mode === "stale";
    const key = stale ? "stale" : isLive ? "live" : "sim";
    if (lastModeKey === key) return;
    lastModeKey = key;
    if (stale) {
      badge.textContent = "● Sensor Stale";
      badge.title = "Last sensor update is older than 30s — waiting for next reading.";
    } else if (isLive) {
      badge.textContent = "● Live Mode";
      badge.title = "Live sensor stream detected";
    } else {
      badge.textContent = "◆ Simulation";
      badge.title = "Simulation mode — toggle a real sensor in Settings → Sensors";
    }
    badge.classList.toggle("home-mode-live", isLive && !stale);
    badge.classList.toggle("home-mode-sim", !isLive && !stale);
  }

  function renderStats(summary, healthData) {
    const healthy = safeNum(summary && summary.healthy);
    const warn = safeNum(summary && summary.warning);
    const crit = safeNum(summary && summary.critical);
    const total = Math.max(1, healthy + warn + crit);
    const key = healthy + ":" + warn + ":" + crit + ":" + (healthData ? healthData.plant_health : "-");
    if (key === lastStatsKey) return;
    lastStatsKey = key;

    const set = (id, txt) => {
      const el = $(id);
      if (el && el.textContent !== txt) el.textContent = txt;
    };
    const setNum = (id, val) => {
      const el = $(id);
      if (!el) return;
      const next = String(val);
      if (el.textContent === next) return;
      el.textContent = next;
      el.classList.remove("is-updated");
      void el.offsetWidth;
      el.classList.add("is-updated");
      const card = el.closest(".stat-card");
      if (card) card.classList.toggle("is-zero", val === 0);
    };
    const setFill = (id, pct) => {
      const el = $(id);
      if (el) el.style.setProperty("--w", Math.max(2, Math.min(100, pct)) + "%");
    };

    setNum("home-stat-healthy", healthy);
    setNum("home-stat-warn", warn);
    setNum("home-stat-crit", crit);

    setFill("home-stat-healthy-fill", (healthy / total) * 100);
    setFill("home-stat-warn-fill", (warn / total) * 100);
    setFill("home-stat-crit-fill", (crit / total) * 100);

    const hp = healthData && typeof healthData.plant_health === "number" ? healthData.plant_health : null;
    set(
      "home-stat-healthy-sub",
      hp != null ? "Plant health " + hp + "%" : healthy > 0 ? "Operational" : "Awaiting sensor data"
    );
    set("home-stat-warn-sub", warn > 0 ? "Investigate soon" : "All zones clear");
    set("home-stat-crit-sub", crit > 0 ? "Immediate action" : "No critical zones");
  }

  function updateScannerFoot(lastScan, lastHealth, isLive) {
    const meta = $("home-scan-meta-top");
    const status = $("home-scan-status");
    const idEl = $("home-scanner-id");
    if (!meta || !status) return;

    const key =
      (lastScan ? lastScan.scan_id + ":" + lastScan.confidence + ":" + lastScan.timestamp : "0") +
      "|" +
      (lastHealth ? lastHealth.plant_health : "-") +
      "|" +
      (isLive ? "L" : "S");
    if (key === lastFootKey) return;
    lastFootKey = key;

    if (lastScan) {
      const conf = ((lastScan.confidence || 0) * 100).toFixed(1);
      meta.textContent = "Plant Vision · " + conf + "% confidence · " + fmtAgo(lastScan.timestamp);
      const hp = lastHealth && typeof lastHealth.plant_health === "number" ? lastHealth.plant_health : null;
      status.textContent = hp != null
        ? "● " + lastScan.disease + " — Health " + hp + "%"
        : "● " + lastScan.disease + " — last scan";
      status.classList.remove("st-warn", "st-crit");
      if (lastScan.status === "WARN") status.classList.add("st-warn");
      else if (lastScan.status === "CRITICAL") status.classList.add("st-crit");
      if (idEl && lastScan.scan_id) idEl.textContent = lastScan.scan_id;
    } else {
      meta.textContent = isLive ? "Plant Vision · Live mode · Cucumber" : "Plant Vision v4.2 · Simulation · Cucumber";
      status.textContent = "● Awaiting leaf — point camera at a target plant";
      status.classList.remove("st-warn", "st-crit");
    }
  }

  function updateLogPulse(lastEvent) {
    const pulse = $("home-log-pulse");
    const text = $("home-log-pulse-text");
    if (!pulse || !text) return;
    if (!lastEvent) {
      pulse.hidden = true;
      lastPulseKey = "";
      return;
    }
    const key = (lastEvent.id || lastEvent.timestamp) + ":" + (lastEvent.message || "");
    if (key === lastPulseKey) return;
    lastPulseKey = key;
    pulse.hidden = false;
    const ago = fmtAgo(lastEvent.timestamp);
    const msg = (lastEvent.message || "").length > 64
      ? lastEvent.message.slice(0, 63) + "…"
      : lastEvent.message || "Pulse received";
    text.textContent = msg + " · " + ago;
  }

  function emptyStateHTML() {
    return (
      '<div class="home-log-empty" id="home-log-empty">' +
      '<div class="home-log-empty-ico" aria-hidden="true">' +
      '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>' +
      "</div>" +
      "<strong>No scans yet</strong>" +
      "<span>Run a scan to see results land here in real time.</span>" +
      "</div>"
    );
  }

  function showLogEmpty(empty) {
    const grid = $("home-log-grid");
    if (!grid) return;
    const hasEntries = grid.querySelector(".entry");
    const emptyEl = $("home-log-empty");
    if (empty && !hasEntries) {
      if (!emptyEl) grid.innerHTML = emptyStateHTML();
      else emptyEl.style.display = "";
      const countEl = $("home-log-count");
      if (countEl) countEl.textContent = "0 entries";
    } else if (!empty && emptyEl) {
      emptyEl.style.display = "none";
    }
  }

  async function refresh() {
    if (!window.PLANT_API_BASE) {
      setMode(false);
      return;
    }

    let summary = null;
    let history = null;
    let events = null;
    let health = null;
    let isLive = false;
    let sensorCtx = null;

    try {
      const [gardenRes, histRes, evRes, healthRes, ctx] = await Promise.all([
        typeof fetchGardenDashboard === "function" ? fetchGardenDashboard() : Promise.resolve({ ok: false, data: null }),
        typeof fetchAnalyticsHistory === "function" ? fetchAnalyticsHistory(3) : Promise.resolve(null),
        typeof fetchAnalyticsEvents === "function" ? fetchAnalyticsEvents(1) : Promise.resolve(null),
        typeof fetchPlantHealth === "function" ? fetchPlantHealth() : Promise.resolve(null),
        window.plantSensor && typeof window.plantSensor.get === "function"
          ? window.plantSensor.get()
          : Promise.resolve(null),
      ]);

      if (gardenRes && gardenRes.ok && gardenRes.data) {
        summary = gardenRes.data.summary || null;
        isLive = gardenRes.data.source === "live";
      }
      if (Array.isArray(histRes)) history = histRes;
      if (Array.isArray(evRes)) events = evRes;
      if (healthRes && healthRes.plant_health !== undefined) health = healthRes;
      sensorCtx = ctx || null;
      // Unified source of truth: a fresh sensor reading always promotes
      // Home to Live mode, even before any scans have happened.
      if (sensorCtx && (sensorCtx.mode === "live" || sensorCtx.mode === "stale")) {
        isLive = true;
      }
    } catch (_) {
      /* keep last UI state */
    }

    setMode(isLive, sensorCtx);
    renderStats(summary, health);
    updateScannerFoot(history && history[0], health, isLive);
    updateLogPulse(events && events[0]);
    renderLogEntries(history);
    showLogEmpty(!history || history.length === 0);
  }

  function statusTagClass(st) {
    if (st === "PASS" || st === "HEALTHY") return "et-ok";
    if (st === "CRITICAL" || st === "FAIL") return "et-crit";
    return "et-warn";
  }

  // Render the Home scan log directly so a fresh page load (without
  // navigating to Analytics first) still shows the latest scans.
  function renderLogEntries(rows) {
    const grid = $("home-log-grid")
      || document.querySelector("#page-home .log-grid");
    const countEl = $("home-log-count")
      || document.querySelector("#page-home .log-count");
    if (!grid) return;
    const slice = Array.isArray(rows) ? rows.slice(0, 3) : [];
    if (countEl) countEl.textContent = slice.length + " entries";
    if (!slice.length) return;
    const html = slice
      .map((r) => {
        const cls = statusTagClass(r.status);
        const thumbCls = (r.status === "WARN" || r.status === "CRITICAL") ? "entry-t-warn" : "";
        const img = r.status === "PASS" ? "healthy_leaf.png" : "diseased_leaf.png";
        return `<article class="entry" data-scan-id="${r.scan_id}">
          <div class="entry-thumb ${thumbCls}"><img src="${img}" alt="" class="entry-img"></div>
          <div class="entry-body">
            <div class="entry-r1">
              <span class="entry-name">${r.disease}</span>
              <span class="entry-tag ${cls}">${r.status}</span>
            </div>
            <span class="entry-sub mono">${fmtAgo(r.timestamp)} · ${(r.confidence * 100).toFixed(1)}% · ${r.scan_id}</span>
          </div>
        </article>`;
      })
      .join("");
    if (grid.innerHTML !== html) grid.innerHTML = html;
  }

  function onNavigate(targetId) {
    if (targetId === "page-home") {
      refresh();
      if (!pollTimer) pollTimer = setInterval(refresh, POLL_MS);
    }
  }

  function start() {
    if (pollTimer) return;
    refresh();
    pollTimer = setInterval(refresh, POLL_MS);
  }

  window.plantHome = {
    refresh,
    onNavigate,
    start,
    stop: () => {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
