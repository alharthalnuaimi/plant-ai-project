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
        // Prefer the rich shape (image_url, plant_id, classified status) so
        // the Home log can render thumbnails + premium placeholders.
        typeof fetchScanHistory === "function" ? fetchScanHistory({ limit: 3 })
          : (typeof fetchAnalyticsHistory === "function" ? fetchAnalyticsHistory(3) : Promise.resolve(null)),
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
      // Accept both shapes: rich { scans: [...] } and legacy array.
      if (histRes && Array.isArray(histRes.scans)) history = histRes.scans;
      else if (Array.isArray(histRes)) history = histRes;
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

  // Final polish — friendly status / disease / confidence helpers.
  // Mirror analytics.js so Home / Analytics / Profile / Assistant all
  // present the same wording for legacy + low-quality scan rows.
  const _UNCLASSIFIED = new Set(["", "unknown", "pending", "pending analysis", "unclassified", "n/a"]);
  function _isUnclassified(r) {
    if (!r) return true;
    const d = (r.disease || "").trim().toLowerCase();
    return !d || _UNCLASSIFIED.has(d);
  }
  function _friendlyDisease(r) {
    if (_isUnclassified(r)) return "Pending analysis";
    return r.disease;
  }
  function _friendlyConfidence(r) {
    if (_isUnclassified(r)) return "—";
    const c = Number(r && r.confidence);
    if (!Number.isFinite(c) || c <= 0) return "—";
    return (c * 100).toFixed(1) + "%";
  }
  function _friendlyStatusLabel(s) {
    if (s === "PASS") return "Healthy";
    if (s === "WARN") return "Warning";
    if (s === "CRITICAL") return "Critical";
    if (s === "UNKNOWN") return "Unclassified";
    return s || "Warning";
  }
  function _resolveThumbUrl(r) {
    if (!r) return null;
    const base = window.PLANT_API_BASE || "";
    const meta = r.metadata || {};
    const url = r.image_url || meta.image_url || null;
    if (url) return /^https?:\/\//i.test(url) ? url : `${base}${url.startsWith("/") ? "" : "/"}${url.replace(/\\/g, "/")}`;
    const path = r.image_path || meta.saved_path || null;
    if (!path) return null;
    return `${base}${path.startsWith("/") ? "" : "/"}${path.replace(/\\/g, "/")}`;
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
        const thumbUrl = _resolveThumbUrl(r);
        const disease = _friendlyDisease(r);
        const conf = _friendlyConfidence(r);
        const stLbl = _friendlyStatusLabel(r.status);
        const shortId = r.id ? String(r.id).slice(0, 8) : (r.scan_id || "");
        const time = (typeof r.timestamp === "number")
          ? fmtAgo(r.timestamp)
          : (r.created_at ? fmtAgo(Math.floor(Date.parse(r.created_at) / 1000)) : "—");
        const inner = thumbUrl
          ? `<img src="${thumbUrl}" alt="" class="entry-img" loading="lazy" onerror="this.parentNode.classList.add('entry-thumb-placeholder');this.outerHTML='<span class=\\'entry-thumb-empty\\'><svg viewBox=\\'0 0 24 24\\' fill=\\'none\\' stroke=\\'currentColor\\' stroke-width=\\'1.5\\' stroke-linecap=\\'round\\' stroke-linejoin=\\'round\\'><path d=\\'M11 20A7 7 0 0 1 4 13V4h9a7 7 0 0 1 7 7v9z\\'/><path d=\\'M4 4l16 16\\'/></svg><span class=\\'entry-thumb-empty-lbl\\'>No image stored</span></span>'">`
          : `<span class="entry-thumb-empty" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 4 13V4h9a7 7 0 0 1 7 7v9z"/><path d="M4 4l16 16"/></svg><span class="entry-thumb-empty-lbl">No image stored</span></span>`;
        return `<article class="entry" data-scan-id="${r.id || r.scan_id || ""}">
          <div class="entry-thumb${thumbUrl ? "" : " entry-thumb-placeholder"}">${inner}</div>
          <div class="entry-body">
            <div class="entry-r1">
              <span class="entry-name">${disease}</span>
              <span class="entry-tag ${cls}">${stLbl}</span>
            </div>
            <span class="entry-sub mono">${time} · ${conf}${shortId ? " · " + shortId : ""}</span>
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

  // --- Phase 3: Scan-zone picker (Home → /predict zone_id) --------------
  // Priority resolution: explicit Home selection > Garden selection
  //                    > window.PLANT_ZONE_ID > "zone_alpha".
  // We persist the Home picker selection in localStorage so it survives
  // page reload, but we DO NOT mutate window.PLANT_ZONE_ID (which is the
  // operator's session zone). The scan pipeline calls getScanTargetZone()
  // at scan time so the latest Garden selection still wins if the user
  // moves between Garden and Home.
  let _homeScanZone = null;
  function _initScanZonePicker() {
    const sel = document.getElementById("scan-zone-select");
    const wrap = document.getElementById("scan-zone-picker");
    if (!sel) return;
    const stored = localStorage.getItem("pv-home-scan-zone");
    const fallback = (window.PLANT_ZONE_ID || "zone_alpha").trim();
    _homeScanZone = stored || fallback;
    // Populate from /zones if available, otherwise keep the static options.
    if (typeof fetchZones === "function") {
      try {
        Promise.resolve(fetchZones()).then((res) => {
          if (!res || !Array.isArray(res.zones)) return;
          sel.innerHTML = res.zones
            .map((z) => `<option value="${z.slug}">${z.name || z.slug}</option>`)
            .join("");
          sel.value = _homeScanZone;
        }).catch(() => { /* keep static fallback */ });
      } catch (_) { /* keep static fallback */ }
    }
    sel.value = _homeScanZone;
    sel.addEventListener("change", () => {
      _homeScanZone = sel.value || fallback;
      localStorage.setItem("pv-home-scan-zone", _homeScanZone);
      if (wrap) wrap.removeAttribute("data-source");
    });
    // If Garden has a current selection, follow it visually (and update the
    // picker UX) — but the resolver below always re-reads at scan time.
    window.addEventListener("plantvision:garden-zone-selected", (e) => {
      const z = e && e.detail && e.detail.zone_id;
      if (!z) return;
      sel.value = z;
      _homeScanZone = z;
      if (wrap) wrap.setAttribute("data-source", "garden");
    });
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", _initScanZonePicker);
  } else {
    _initScanZonePicker();
  }

  function getScanTargetZone() {
    const gardenSel =
      (window.plantGarden && typeof window.plantGarden.getSelectedZoneSlug === "function")
        ? window.plantGarden.getSelectedZoneSlug()
        : null;
    return (gardenSel || _homeScanZone || window.PLANT_ZONE_ID || "zone_alpha").trim() || "zone_alpha";
  }

  window.plantHome = {
    refresh,
    onNavigate,
    start,
    getScanTargetZone,
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
