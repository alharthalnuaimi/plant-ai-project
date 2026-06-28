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
      badge.textContent = "● Simulation";
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
      meta.textContent = isLive ? "Plant Vision · Live mode" : "Plant Vision v4.2 · Simulation";
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
    // In Demo Mode the fixtures answer every fetch — we still want to
    // run the rest of the pipeline so the UI renders fake-but-coherent
    // data even when window.PLANT_API_BASE is unset.
    const demoOn = !!(window.plantDemo && window.plantDemo.isOn && window.plantDemo.isOn());
    if (!demoOn && !window.PLANT_API_BASE) {
      setMode(false);
      return;
    }

    let summary = null;
    let history = null;
    let events = null;
    let health = null;
    let isLive = false;
    let sensorCtx = null;
    let report = null;

    try {
      const [gardenRes, histRes, evRes, healthRes, ctx, reportRes] = await Promise.all([
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
        // Phase 4 (B1): unified /report — gives us care + warnings in one
        // call. Returns null if the JSON path 400s (no plant_id yet);
        // that's OK — we fall back to /health/plant + /sensor/latest.
        typeof fetchUnifiedReport === "function"
          ? fetchUnifiedReport(window.PLANT_ID || "cucumber_001")
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
      if (reportRes && reportRes.scores) report = reportRes;
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
    // Phase 4 (B1)
    renderHeroHealth(health, history && history[0]);
    renderWarnings(report, health, sensorCtx);
    renderCareCard(report);
    // Phase Final — health-score trend chart (last 7 scans).
    renderHealthTrend();
  }

  // -----------------------------------------------------------------
  // Phase Final — Health-score trend chart (last 7 scans on Home).
  //
  // Loads Chart.js from CDN (see index.html). Pulls /scans/history
  // ?limit=7 (Demo Mode short-circuit honoured via api.js), plots
  // health_score over created_at. Hidden when fewer than 2 points
  // exist or Chart.js failed to load — caller never crashes.
  // -----------------------------------------------------------------
  let _trendChart = null;
  async function renderHealthTrend() {
    const card = $("home-trend-card");
    const canvas = $("home-trend-canvas");
    const empty = $("home-trend-empty");
    if (!card || !canvas) return;
    if (typeof window.Chart !== "function") {
      // CDN blocked / offline — degrade gracefully.
      card.hidden = true;
      return;
    }

    let payload = null;
    try {
      payload = typeof fetchScanHistory === "function"
        ? await fetchScanHistory({ limit: 7 })
        : null;
    } catch (_) { payload = null; }

    const scans = (payload && Array.isArray(payload.scans)) ? payload.scans : [];
    // Keep only scans with a usable health_score, then oldest → newest.
    const series = scans
      .filter((s) => typeof s.health_score === "number" && !Number.isNaN(s.health_score))
      .sort((a, b) => {
        const ta = a.created_at ? Date.parse(a.created_at) : (a.timestamp || 0) * 1000;
        const tb = b.created_at ? Date.parse(b.created_at) : (b.timestamp || 0) * 1000;
        return ta - tb;
      })
      .slice(-7);

    if (series.length < 2) {
      card.hidden = false;
      if (empty) empty.hidden = false;
      // Destroy any prior chart so the empty message is visible.
      if (_trendChart) { _trendChart.destroy(); _trendChart = null; }
      return;
    }

    card.hidden = false;
    if (empty) empty.hidden = true;

    const labels = series.map((s) => {
      const t = s.created_at ? new Date(s.created_at) : new Date((s.timestamp || 0) * 1000);
      return t.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    });
    const data = series.map((s) => Math.round(s.health_score));
    const lastScore = data[data.length - 1];

    // Tone the line + tag with the same thresholds as the hero ring.
    let toneColor = "#8ca88c"; // --sage
    if (lastScore < 50) toneColor = "#b07070"; // --coral
    else if (lastScore < 75) toneColor = "#c0a06a"; // --gold
    const tag = $("home-trend-tag");
    if (tag) tag.style.color = toneColor;

    const ds = {
      label: "Plant health",
      data: data,
      borderColor: toneColor,
      backgroundColor: toneColor + "22",
      tension: 0.32,
      borderWidth: 2,
      pointRadius: 3,
      pointBackgroundColor: toneColor,
      pointBorderColor: "rgba(255,255,255,0.6)",
      pointBorderWidth: 1,
      fill: true,
    };

    if (_trendChart) {
      _trendChart.data.labels = labels;
      _trendChart.data.datasets = [ds];
      _trendChart.update("none");
      return;
    }

    try {
      _trendChart = new window.Chart(canvas.getContext("2d"), {
        type: "line",
        data: { labels: labels, datasets: [ds] },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: { duration: 280 },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: "rgba(35,40,48,0.95)",
              titleColor: "#d4dae2",
              bodyColor: "#d4dae2",
              borderColor: "rgba(140,168,140,0.32)",
              borderWidth: 1,
              cornerRadius: 6,
              displayColors: false,
              callbacks: {
                label: (ctx) => " Health " + ctx.parsed.y + " / 100",
              },
            },
          },
          scales: {
            x: {
              ticks: { color: "rgba(148,163,156,0.7)", font: { family: "IBM Plex Mono", size: 9 } },
              grid: { color: "rgba(255,255,255,0.04)" },
            },
            y: {
              min: 0,
              max: 100,
              ticks: { color: "rgba(148,163,156,0.7)", font: { family: "IBM Plex Mono", size: 9 }, stepSize: 25 },
              grid: { color: "rgba(255,255,255,0.04)" },
            },
          },
        },
      });
    } catch (_) {
      card.hidden = true;
    }
  }

  // -----------------------------------------------------------------
  // Phase 4 (B1) — Hero plant-health ring on the scanner card.
  // -----------------------------------------------------------------
  const HHR_CIRC = 2 * Math.PI * 17; // r=17 → circumference ≈ 106.81
  function renderHeroHealth(health, latestScan) {
    const card = $("home-hero-health");
    if (!card) return;
    const score = health && typeof health.plant_health === "number"
      ? Math.max(0, Math.min(100, Math.round(health.plant_health)))
      : null;
    if (score == null) {
      card.hidden = true;
      return;
    }
    card.hidden = false;
    const val = $("home-hero-val");
    if (val) val.textContent = String(score);
    const fill = $("home-hero-ring-fill");
    if (fill) {
      fill.setAttribute("stroke-dasharray", HHR_CIRC.toFixed(2));
      fill.setAttribute("stroke-dashoffset", (HHR_CIRC * (1 - score / 100)).toFixed(2));
    }
    let tone = "tone-ok";
    if (score < 50) tone = "tone-crit";
    else if (score < 75) tone = "tone-warn";
    card.classList.remove("tone-ok", "tone-warn", "tone-crit");
    card.classList.add(tone);

    const title = $("home-hero-title");
    const sub = $("home-hero-sub");
    if (title) {
      if (latestScan && latestScan.disease) {
        title.textContent = latestScan.disease;
      } else if (tone === "tone-crit") title.textContent = "Critical — act now";
      else if (tone === "tone-warn") title.textContent = "Needs attention";
      else title.textContent = "Healthy plant";
    }
    if (sub) {
      const risk = (health.disease_risk || "—").toString();
      const env = (health.environment_stress || "stable").toString();
      sub.textContent = "Risk " + risk + " · Env " + env;
    }
  }

  // -----------------------------------------------------------------
  // Phase 4 (B1) — Warnings strip
  //   Source priority: /report.warnings (rich) → health.recommendation
  //   → sensor stress heuristic. Hidden when nothing actionable.
  // -----------------------------------------------------------------
  function renderWarnings(report, health, sensorCtx) {
    const host = $("home-warnings");
    const list = $("home-warnings-list");
    if (!host || !list) return;
    const items = [];
    if (report && Array.isArray(report.warnings)) {
      report.warnings.forEach((w) => {
        items.push({
          severity: w.severity || "warning",
          message: w.message || (w.category ? w.category + " out of range" : "warning"),
        });
      });
    }
    if (!items.length && health && health.disease_risk && health.disease_risk !== "low" && health.recommendation) {
      items.push({ severity: health.disease_risk === "high" ? "critical" : "warning", message: health.recommendation });
    }
    if (!items.length && sensorCtx && sensorCtx.reading && sensorCtx.reading.status) {
      const st = sensorCtx.reading.status;
      if (st.overall_environment_status === "stressed") {
        items.push({ severity: "warning", message: "Environment stressed — see sensor readings" });
      }
    }
    if (!items.length) {
      host.hidden = true;
      list.innerHTML = "";
      return;
    }
    host.hidden = false;
    const html = items.slice(0, 4).map((w) => {
    const sev = (w.severity || "warning").toLowerCase();
      const cls = sev === "critical" ? "sev-critical" : "sev-warning";
      const icoSvg = sev === "critical"
        ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
        : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>';
      const msg = String(w.message).length > 108 ? String(w.message).slice(0, 107) + "…" : w.message;
      return '<span class="home-warn-chip ' + cls + '"><span class="home-warn-chip-dot"></span><span class="home-warn-ico" aria-hidden="true">' + icoSvg + '</span> ' + _escape(msg) + '</span>';
    }).join("");
    list.innerHTML = html;
  }

  // -----------------------------------------------------------------
  // Phase 4 (B1) — Care card (latest care plan)
  // -----------------------------------------------------------------
  function renderCareCard(report) {
    const card = $("home-care-card");
    if (!card) return;
    if (!report || !report.care_plan && !(report.scores && report.plant_id)) {
      // Hide when there's no scan yet (i.e. /report has no plant context).
      card.hidden = true;
      return;
    }
    const template = (report.care_plan && report.care_plan.template) || null;
    const water = template && template.watering && template.watering.frequency
      ? template.watering.frequency
      : (template && template.watering && template.watering.soil_moisture_target
          ? _range(template.watering.soil_moisture_target, "%")
          : "—");
    const sun = template && template.sunlight && template.sunlight.hours_per_day
      ? _range(template.sunlight.hours_per_day, "h")
      : "—";
    const temp = template && template.temperature_c ? _range(template.temperature_c, "°C") : "—";
    const hum = template && template.humidity_pct ? _range(template.humidity_pct, "%") : "—";
    const stage = (report.current_growth_stage) || (report.care_plan && report.care_plan.current_stage && report.care_plan.current_stage.name) || "—";
    const summary = report.analysis_summary
      || (report.care_recommendations && report.care_recommendations[0] && report.care_recommendations[0].message)
      || "Care plan available — see Garden + Profile pages for full details.";

    // Hide entirely when we have no template (i.e. report came back without
    // a care_plan AND the explanation block is empty) — avoids an empty card.
    if (!template && !report.analysis_summary && !(report.care_recommendations && report.care_recommendations.length)) {
      card.hidden = true;
      return;
    }
    card.hidden = false;

    const set = (id, txt) => { const el = $(id); if (el && el.textContent !== txt) el.textContent = txt; };
    set("home-care-stage", stage ? stage.toUpperCase() : "—");
    set("home-care-water", water);
    set("home-care-sun", sun);
    set("home-care-temp", temp);
    set("home-care-hum", hum);
    set("home-care-summary", summary);
  }

  function _range(arr, unit) {
    if (!Array.isArray(arr) || arr.length < 2) return "—";
    return arr[0] + "–" + arr[1] + (unit || "");
  }
  function _escape(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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

  function _markBootstrap(on) {
    // Show pulsing skeleton on the three Home stat cards until the
    // first refresh resolves. Pure visual — no contract change.
    const cards = document.querySelectorAll(".stats-row .stat-card");
    cards.forEach((c) => c.classList.toggle("is-bootstrap", !!on));
  }

  function start() {
    if (pollTimer) return;
    _markBootstrap(true);
    // refresh() is async — clear the bootstrap class once the first
    // pass resolves (success OR failure both end the skeleton).
    Promise.resolve(refresh()).finally(() => _markBootstrap(false));
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

  // Phase 4: react to Demo Mode toggles immediately so Home's hero ring,
  // warnings strip, care card, and trend chart swap between live + fixture
  // without waiting for the poll cycle.
  window.addEventListener("plantvision:demo-mode-changed", () => {
    // Reset cache keys so the next refresh re-renders even when payloads
    // happen to be byte-identical.
    lastModeKey = "";
    lastStatsKey = "";
    lastFootKey = "";
    lastPulseKey = "";
    refresh();
  });
})();
