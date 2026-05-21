/**
 * PlantVision Analytics Dashboard — live data from /analytics/*
 * Updates in-place to avoid flicker; refreshes on Data page open and after scans.
 */
(function () {
  const POLL_MS = 5000;
  const DEBUG = Boolean(window.PLANT_ANALYTICS_DEBUG);

  let pollTimer = null;
  let lastRefreshAt = 0;
  let lastEventId = null;
  let refreshInFlight = false;
  let lastSnapshot = {
    summary: "",
    history: "",
    events: "",
    zones: "",
    insights: "",
    diseases: "",
    outcomes: "",
  };
  let barsInitialized = false;
  let zoneCardEls = new Map();

  function log(...args) {
    if (DEBUG) console.log("[analytics]", ...args);
  }

  function apiBase() {
    return window.PLANT_API_BASE;
  }

  function stableStringify(v) {
    try {
      return JSON.stringify(v);
    } catch (_) {
      return "";
    }
  }

  async function fetchJson(path) {
    const base = apiBase();
    if (!base) {
      log("no PLANT_API_BASE");
      return { ok: false, error: "no_api_base", data: null };
    }
    try {
      const resp = await fetch(`${base}${path}`, { method: "GET" });
      if (!resp.ok) {
        log("HTTP", path, resp.status);
        return { ok: false, error: `http_${resp.status}`, data: null };
      }
      const data = await resp.json();
      return { ok: true, data };
    } catch (e) {
      log("fetch failed", path, e.message);
      return { ok: false, error: e.message || "network", data: null };
    }
  }

  function isDataPageActive() {
    const page = document.getElementById("page-data");
    return page && page.classList.contains("active");
  }

  function fmtAgo(ts) {
    const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (sec < 60) return sec + "s ago";
    if (sec < 3600) return Math.floor(sec / 60) + "m ago";
    if (sec < 86400) return Math.floor(sec / 3600) + "h ago";
    return Math.floor(sec / 86400) + "d ago";
  }

  function fmtTime(ts) {
    return new Date(ts * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function zoneLabel(zid) {
    return (zid || "zone")
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase());
  }

  function statusTagClass(status) {
    if (status === "PASS" || status === "HEALTHY") return "et-ok";
    if (status === "CRITICAL") return "et-crit";
    return "et-warn";
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el && el.textContent !== text) {
      el.classList.add("metric-updating");
      el.textContent = text;
      window.setTimeout(() => el.classList.remove("metric-updating"), 220);
    }
  }

  function setRing(id, pct) {
    const el = document.getElementById(id);
    if (!el) return;
    const circ = 2 * Math.PI * 50;
    const off = circ * (1 - Math.min(1, Math.max(0, pct / 100)));
    el.setAttribute("stroke-dasharray", String(circ));
    el.setAttribute("stroke-dashoffset", String(off));
  }

  function drawLineChart(canvas, values) {
    if (!canvas || !values || !values.length) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const cw = canvas.clientWidth || 300;
    const ch = canvas.clientHeight || 120;
    canvas.width = cw * dpr;
    canvas.height = ch * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);

    const pad = { t: 12, r: 12, b: 24, l: 36 };
    const innerW = cw - pad.l - pad.r;
    const innerH = ch - pad.t - pad.b;
    const min = Math.min(...values) * 0.95;
    const max = Math.max(...values) * 1.02 || 1;
    const range = max - min || 0.1;
    const sage =
      getComputedStyle(document.documentElement).getPropertyValue("--sage").trim() ||
      "#8ca88c";

    for (let i = 0; i <= 4; i++) {
      const y = pad.t + (innerH * i) / 4;
      ctx.strokeStyle = "rgba(140,168,140,0.08)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(pad.l, y);
      ctx.lineTo(cw - pad.r, y);
      ctx.stroke();
    }

    const pts = values.map((v, i) => ({
      x: pad.l + (innerW * i) / Math.max(1, values.length - 1),
      y: pad.t + innerH - ((v - min) / range) * innerH,
    }));

    const grad = ctx.createLinearGradient(0, pad.t, 0, ch - pad.b);
    grad.addColorStop(0, "rgba(140,168,140,0.22)");
    grad.addColorStop(1, "rgba(140,168,140,0)");
    ctx.beginPath();
    ctx.moveTo(pts[0].x, ch - pad.b);
    pts.forEach((p) => ctx.lineTo(p.x, p.y));
    ctx.lineTo(pts[pts.length - 1].x, ch - pad.b);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    ctx.beginPath();
    pts.forEach((p, i) =>
      i === 0 ? ctx.moveTo(p.x, p.y) : ctx.lineTo(p.x, p.y)
    );
    ctx.strokeStyle = sage;
    ctx.lineWidth = 2;
    ctx.stroke();

    const last = pts[pts.length - 1];
    ctx.fillStyle = sage;
    ctx.beginPath();
    ctx.arc(last.x, last.y, 4, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawSparkline(canvas, values) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const cw = canvas.clientWidth || 80;
    const ch = canvas.clientHeight || 28;
    canvas.width = cw * dpr;
    canvas.height = ch * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    if (!values || values.length < 2) {
      ctx.strokeStyle = "rgba(140,168,140,0.15)";
      ctx.setLineDash([3, 3]);
      ctx.beginPath();
      ctx.moveTo(0, ch / 2);
      ctx.lineTo(cw, ch / 2);
      ctx.stroke();
      return;
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = max - min || 1;
    const sage =
      getComputedStyle(document.documentElement).getPropertyValue("--sage").trim() ||
      "#8ca88c";
    ctx.beginPath();
    values.forEach((v, i) => {
      const x = (cw * i) / (values.length - 1);
      const y = ch - 2 - ((v - min) / range) * (ch - 4);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = sage;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([]);
    ctx.stroke();
  }

  function ensureActivityBars(days) {
    const wrap = document.getElementById("chart-bars-live");
    if (!wrap || !days) return;
    if (!wrap.querySelector(".chart-bar-count")) barsInitialized = false;
    if (!barsInitialized || wrap.children.length !== days.length) {
      wrap.innerHTML = days
        .map(
          (d) => `
        <div class="chart-col">
          <span class="chart-bar-count mono" data-day="${d.day}"></span>
          <div class="chart-bar chart-bar-live" data-day="${d.day}" style="--h:8%"></div>
          <span class="chart-day">${d.day}</span>
        </div>`
        )
        .join("");
      barsInitialized = true;
    }
    const dayMap = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    const todayLabel = dayMap[new Date().getDay()];
    days.forEach((d) => {
      const bar = wrap.querySelector(`.chart-bar-live[data-day="${d.day}"]`);
      const cnt = wrap.querySelector(`.chart-bar-count[data-day="${d.day}"]`);
      const hPct = d.count > 0 ? Math.max(d.pct || 0, 12) : 8;
      const h = `${hPct}%`;
      if (bar) {
        if (bar.style.getPropertyValue("--h") !== h) bar.style.setProperty("--h", h);
        bar.classList.toggle("chart-bar-today", d.day === todayLabel);
      }
      if (cnt) cnt.textContent = d.count > 0 ? String(d.count) : "";
    });
  }

  function renderScanOutcomes(slices, isLive) {
    const el = document.getElementById("outcomes-list-live");
    const tag = document.getElementById("outcomes-tag");
    if (!el) return;
    const list = slices || [];
    const key = stableStringify(list);
    if (lastSnapshot.outcomes === key) return;
    lastSnapshot.outcomes = key;
    if (tag) tag.textContent = isLive ? "From scans" : "Baseline";

    if (!list.length || (list.length === 1 && list[0].count === 0)) {
      el.innerHTML =
        '<div class="d-list-item d-list-placeholder"><span class="d-list-name">No scan outcomes yet</span><span class="d-list-val">—</span></div>';
      return;
    }
    el.innerHTML = list
      .map((s) => {
        const tone = s.tone || "neutral";
        const fillCls =
          tone === "pass"
            ? "sf-pass outcomes-fill"
            : tone === "crit"
              ? "sf-crit outcomes-fill"
              : tone === "warn"
                ? "sf-warn outcomes-fill"
                : "";
        const pct = s.pct != null ? s.pct : 0;
        const val =
          s.count != null && s.count > 0 ? `${s.count} · ${pct}%` : `${pct}%`;
        return `<div class="d-list-item">
          <span class="d-list-name">${s.label}</span>
          <span class="d-list-val">${val}</span>
          <div class="d-list-bar"><div class="d-list-fill ${fillCls}" style="--w:${pct}%"></div></div>
        </div>`;
      })
      .join("");
  }

  function renderRuntimeMetrics(s, isLive) {
    const confPct = (s.avg_confidence * 100).toFixed(1);
    const passPct = (s.pass_rate != null ? s.pass_rate : 0).toFixed(1);
    const latSec = (s.avg_inference_ms / 1000).toFixed(1) + "s";
    const scans = String(s.total_scans);
    const scanCap = Math.min(100, (s.total_scans / 50) * 100);

    setText("perf-avg-conf", confPct + "%");
    setText("perf-pass-rate", passPct + "%");
    setText("perf-latency", latSec);
    setText("perf-scans", scans);

    const note = document.getElementById("perf-note");
    if (note) {
      note.textContent = isLive
        ? "Measured from live /predict responses — not offline validation metrics."
        : "Demo estimates until your first scan completes.";
    }
    const src = document.getElementById("perf-source-tag");
    if (src) src.textContent = isLive ? "● Live runtime" : "● Demo baseline";

    const barConf = document.getElementById("perf-bar-conf");
    const barPass = document.getElementById("perf-bar-pass");
    const barLat = document.getElementById("perf-bar-lat");
    const barScans = document.getElementById("perf-bar-scans");
    if (barConf) barConf.style.setProperty("--w", confPct + "%");
    if (barPass) barPass.style.setProperty("--w", passPct + "%");
    if (barLat)
      barLat.style.setProperty(
        "--w",
        Math.min(100, (s.avg_inference_ms / 8000) * 100) + "%"
      );
    if (barScans) barScans.style.setProperty("--w", scanCap + "%");
  }

  function renderTopDiseases(list) {
    const el = document.getElementById("disease-list-live");
    if (!el || !list) return;
    const key = stableStringify(list);
    if (lastSnapshot.diseases === key) return;
    lastSnapshot.diseases = key;

    if (!list.length) {
      el.innerHTML =
        '<div class="d-list-item d-list-placeholder"><span class="d-list-name">No disease detections yet</span><span class="d-list-val">—</span></div>';
      return;
    }
    el.innerHTML = list
      .map((d) => {
        const cls = d.pct >= 40 ? "df-crit" : d.pct >= 25 ? "df-warn" : "";
        return `<div class="d-list-item">
          <span class="d-list-name">${d.name}</span>
          <span class="d-list-val">${d.pct}%</span>
          <div class="d-list-bar"><div class="d-list-fill ${cls}" style="--w:${d.pct}%"></div></div>
        </div>`;
      })
      .join("");
  }

  function renderScanHistory(rows, isLive) {
    const body = document.getElementById("scan-table-body");
    const tag = document.getElementById("scan-history-tag");
    if (!body) return;
    if (tag) tag.textContent = rows.length ? `Recent ${rows.length}` : "Recent";

    if (!rows.length) {
      body.innerHTML = isLive
        ? '<div class="scan-table-empty">No scans yet — run a scan from Home.</div>'
        : '<div class="scan-table-empty">No scans yet. Demo metrics shown until first scan.</div>';
      return;
    }

    const html = rows
      .map((r) => {
        const cls = statusTagClass(r.status);
        const conf = (r.confidence * 100).toFixed(1) + "%";
        return `<div class="scan-table-row" data-scan-id="${r.scan_id}">
          <span class="mono col-id">${r.scan_id}</span>
          <span class="col-detail">${zoneLabel(r.zone_id)} · ${r.disease}</span>
          <span class="entry-tag ${cls} col-status">${r.status}</span>
          <span class="mono col-conf">${conf}</span>
          <span class="mono col-time">${fmtAgo(r.timestamp)}</span>
        </div>`;
      })
      .join("");

    if (body.innerHTML !== html) body.innerHTML = html;
  }

  function renderHomeLog(rows) {
    const grid = document.querySelector("#page-home .log-grid");
    const countEl = document.querySelector("#page-home .log-count");
    if (!grid) return;
    const slice = rows.slice(0, 3);
    if (countEl) countEl.textContent = slice.length + " entries";
    if (!slice.length) return;

    const html = slice
      .map((r) => {
        const cls = statusTagClass(r.status);
        const thumbCls =
          r.status === "WARN" || r.status === "CRITICAL" ? "entry-t-warn" : "";
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

  function renderEvents(events) {
    const list = document.getElementById("event-feed-list");
    if (!list) return;

    if (!events.length) {
      const empty = '<div class="event-feed-empty">Waiting for live events…</div>';
      if (list.innerHTML !== empty) list.innerHTML = empty;
      return;
    }

    const newestId = events[0].id;
    const isNew = lastEventId && newestId !== lastEventId;
    lastEventId = newestId;

    const html = events
      .map((e, i) => {
        const pulse = isNew && i === 0 ? " event-item-new" : "";
        return `<div class="event-item${pulse}" data-event-id="${e.id}" data-type="${e.event_type}">
          <span class="event-time mono">[${fmtTime(e.timestamp)}]</span>
          <span class="event-msg">${e.message}</span>
        </div>`;
      })
      .join("");

    if (list.innerHTML !== html) list.innerHTML = html;
  }

  function patchZoneCard(card, z) {
    const st = (z.status || "WARNING").toLowerCase();
    card.className = `zone-health-card zh-${st}${z.is_demo ? " zh-demo" : ""}`;
    card.dataset.zoneId = z.zone_id;
    const name = card.querySelector(".zone-health-name");
    const badge = card.querySelector(".zone-health-badge");
    const demoBadge = card.querySelector(".zone-health-badge-demo");
    const note = card.querySelector(".zone-health-note");
    if (name) name.textContent = z.label;
    if (badge) badge.textContent = z.status;
    if (demoBadge) demoBadge.hidden = !z.is_demo;
    if (note) note.textContent = z.status_note || "";

    const metrics = card.querySelector(".zone-health-metrics");
    if (metrics) {
      const temp = z.air_temperature != null ? z.air_temperature.toFixed(1) + "°C" : "—";
      const hum = z.air_humidity != null ? z.air_humidity.toFixed(0) + "%" : "—";
      const ph = z.soil_ph != null ? z.soil_ph.toFixed(1) : "—";
      const ec = z.soil_ec != null ? z.soil_ec.toFixed(1) : "—";
      const texts = [`Temp: ${temp}`, `Humid: ${hum}`, `pH: ${ph}`, `EC: ${ec}`];
      metrics.querySelectorAll("span").forEach((sp, i) => {
        if (texts[i] && sp.textContent !== texts[i]) sp.textContent = texts[i];
      });
    }

    card.querySelectorAll(".zh-spark").forEach((cv) => {
      const key = cv.getAttribute("data-series");
      drawSparkline(cv, (z.sparklines && z.sparklines[key]) || []);
    });
  }

  function createZoneCard(z) {
    const st = (z.status || "WARNING").toLowerCase();
    const article = document.createElement("article");
    article.className = `zone-health-card zh-${st}`;
    article.dataset.zoneId = z.zone_id;
    article.innerHTML = `
      <div class="zone-health-head">
        <span class="zone-health-name">${z.label}</span>
        <span class="zone-health-badge-demo"${z.is_demo ? "" : " hidden"}>AWAITING SENSOR</span>
        <span class="zone-health-badge">${z.status}</span>
      </div>
      <div class="zone-health-metrics mono">
        <span>Temp: —</span><span>Humid: —</span><span>pH: —</span><span>EC: —</span>
      </div>
      <p class="zone-health-note">${z.status_note || ""}</p>
      <div class="zone-health-sparks">
        <canvas class="zh-spark" data-series="air_temperature" width="80" height="28"></canvas>
        <canvas class="zh-spark" data-series="air_humidity" width="80" height="28"></canvas>
      </div>`;
    patchZoneCard(article, z);
    return article;
  }

  function renderZoneCards(zones) {
    const grid = document.getElementById("zone-health-grid");
    const tag = document.getElementById("zone-health-tag");
    if (!grid || !zones) return;

    const empty = grid.querySelector(".zone-health-empty");
    if (!zones.length) {
      zoneCardEls.clear();
      grid.innerHTML =
        '<p class="zone-health-empty">No zones with sensor or scan data yet.</p>';
      if (tag) tag.textContent = "Awaiting data";
      return;
    }
    if (empty) empty.remove();
    if (tag) tag.textContent = zones.some((z) => z.is_demo) ? "Mixed · sensors" : "Live sensors";

    zones.forEach((z) => {
      let card = zoneCardEls.get(z.zone_id) || grid.querySelector(`[data-zone-id="${z.zone_id}"]`);
      if (!card) {
        card = createZoneCard(z);
        grid.appendChild(card);
        zoneCardEls.set(z.zone_id, card);
      } else {
        patchZoneCard(card, z);
        zoneCardEls.set(z.zone_id, card);
      }
    });

    grid.querySelectorAll(".zone-health-card").forEach((card) => {
      const zid = card.dataset.zoneId;
      if (!zones.find((z) => z.zone_id === zid)) card.remove();
    });
  }

  function renderInsights(items, source) {
    const panel = document.getElementById("ai-insights-panel");
    if (!panel) return;
    const srcTag = document.getElementById("ai-insights-source");
    const srcLabel = source === "live" ? "● Live" : "● Advisory";
    if (srcTag && srcTag.textContent !== srcLabel) srcTag.textContent = srcLabel;

    const key = stableStringify({ items, source });
    if (lastSnapshot.insights === key) return;
    lastSnapshot.insights = key;

    if (!items.length) {
      panel.innerHTML =
        '<p class="ai-insight-empty">Run scans and connect sensors for AI insights.</p>';
      return;
    }
    panel.innerHTML = items
      .map(
        (item) => `
      <div class="ai-insight-block ai-sev-${item.severity}">
        <p class="ai-insight-label">AI Insight</p>
        <p class="ai-insight-text">${item.insight}</p>
        <p class="ai-insight-rec"><strong>Recommendation</strong><span class="ai-insight-rec-body">${item.recommendation}</span></p>
      </div>`
      )
      .join("");
  }

  function renderEnvTrends(zones) {
    const z = zones && zones[0];
    if (!z || z.air_temperature == null) return;
    setText("trend-temp", z.air_temperature.toFixed(1) + "°C");
    setText("trend-hum", z.air_humidity.toFixed(0) + "%");
    setText("trend-ph", z.soil_ph.toFixed(1));
    const tempMark = document.getElementById("trend-temp-mark");
    const humMark = document.getElementById("trend-hum-mark");
    const phMark = document.getElementById("trend-ph-mark");
    if (tempMark)
      tempMark.style.left =
        Math.min(95, Math.max(5, ((z.air_temperature - 10) / 30) * 100)) + "%";
    if (humMark) humMark.style.left = Math.min(95, Math.max(5, z.air_humidity)) + "%";
    if (phMark)
      phMark.style.left = Math.min(95, Math.max(5, ((z.soil_ph - 4) / 5) * 100)) + "%";

    const sparks = z.sparklines || {};
    drawSparkline(document.getElementById("spark-temp"), sparks.air_temperature);
    drawSparkline(document.getElementById("spark-hum"), sparks.air_humidity);
    drawSparkline(document.getElementById("spark-ph"), sparks.soil_ph);
    drawSparkline(document.getElementById("spark-ec"), sparks.soil_ec);
  }

  function renderSummary(s) {
    if (!s) return;
    const key = stableStringify(s);
    if (lastSnapshot.summary === key) return;
    lastSnapshot.summary = key;

    const detPct = s.detection_rate;
    const confPct = (s.avg_confidence * 100).toFixed(1);
    const isLive = s.source === "live";

    setText("metric-detection", detPct + "%");
    setText(
      "metric-detection-sub",
      isLive ? "Issue detection rate" : "Demo baseline"
    );
    setRing("ring-detection", detPct);
    setText("d-ring-num", confPct + "%");
    setText("d-ring-lbl", isLive ? "Avg confidence" : "Demo avg");
    setRing("ring-confidence", parseFloat(confPct));

    setText("sm-scans", String(s.total_scans));
    setText("sm-time", (s.avg_inference_ms / 1000).toFixed(1));
    setText("sm-conf", confPct);
    setText("sm-zones", String(s.active_zones));
    setText("sm-devices", String(s.connected_devices));
    setText("sm-species", String(s.scans_today));

    renderScanOutcomes(s.scan_outcomes, isLive);
    renderRuntimeMetrics(s, isLive);

    const liveTag = document.getElementById("analytics-live-tag");
    if (liveTag) {
      const sensorCtx = window.plantSensor && window.plantSensor.last ? window.plantSensor.last() : null;
      let label;
      if (sensorCtx && sensorCtx.mode === "stale") label = "● Sensor Stale";
      else if (sensorCtx && sensorCtx.mode === "live" && (s.total_scans || 0) === 0) label = "● Sensor Live";
      else if (isLive) label = "● Live";
      else label = "● Demo";
      if (liveTag.textContent !== label) liveTag.textContent = label;
      liveTag.style.color = (label.includes("Live") || label.includes("Stale")) ? "var(--sage)" : "var(--t3)";
    }

    ensureActivityBars(s.activity_by_day);
    const canvas = document.getElementById("confidence-chart");
    if (canvas && s.confidence_series && s.confidence_series.length) {
      drawLineChart(canvas, s.confidence_series);
    }
    renderTopDiseases(s.top_diseases);
  }

  function showApiError(msg) {
    const tag = document.getElementById("analytics-live-tag");
    if (tag) {
      tag.textContent = "● Offline";
      tag.style.color = "var(--coral)";
    }
    log("api error", msg);
  }

  async function refreshDashboard(options) {
    const force = options && options.force;
    if (refreshInFlight && !force) return;
    refreshInFlight = true;

    try {
      // Prime unified sensor context first; analytics promotes itself to
      // Live whenever a fresh sensor reading exists, even before any scans.
      let sensorCtx = null;
      if (window.plantSensor && typeof window.plantSensor.get === "function") {
        try { sensorCtx = await window.plantSensor.get(force); } catch (_) {}
      }
      const sensorLive = sensorCtx && (sensorCtx.mode === "live" || sensorCtx.mode === "stale");

      const [sumRes, histRes, evRes, zoneRes, insRes] = await Promise.all([
        fetchJson("/analytics/summary"),
        fetchJson("/analytics/history?limit=12"),
        fetchJson("/analytics/events?limit=25"),
        fetchJson("/analytics/zones"),
        fetchJson("/analytics/insights"),
      ]);

      const anyOk =
        sumRes.ok || histRes.ok || evRes.ok || zoneRes.ok || insRes.ok;
      if (!anyOk) {
        showApiError("backend unreachable");
        return;
      }

      let summary = sumRes.ok ? sumRes.data : null;
      const history = histRes.ok ? histRes.data : null;
      const events = evRes.ok ? evRes.data : null;
      const zones = zoneRes.ok ? zoneRes.data : null;
      const insightsRes = insRes.ok ? insRes.data : null;

      // Promote summary.source to "live" when a fresh sensor reading exists.
      // (Backend reports "demo" until a scan happens; we want Live indicator
      // to flip on real sensor data too.)
      if (summary && sensorLive && summary.source !== "live") {
        summary = { ...summary, source: "live" };
      }
      const isLive = summary && summary.source === "live";

      log("refreshed", {
        live: isLive,
        scans: summary && summary.total_scans,
        history: history && history.length,
      });

      if (summary) renderSummary(summary);
      if (history) {
        const histKey = stableStringify(history);
        if (force || lastSnapshot.history !== histKey) {
          lastSnapshot.history = histKey;
          renderScanHistory(history, isLive);
          renderHomeLog(history);
        }
      }
      if (events) {
        const evKey = stableStringify(events);
        if (force || lastSnapshot.events !== evKey) {
          lastSnapshot.events = evKey;
          renderEvents(events);
        }
      }
      if (zones) {
        const zKey = stableStringify(zones);
        if (force || lastSnapshot.zones !== zKey) {
          lastSnapshot.zones = zKey;
          renderZoneCards(zones);
          renderEnvTrends(zones);
        }
      }
      if (insightsRes) {
        renderInsights(insightsRes.items || [], insightsRes.source || (isLive ? "live" : "demo"));
      }
      lastRefreshAt = Date.now();
    } finally {
      refreshInFlight = false;
    }
  }

  function startPolling() {
    if (pollTimer) return;
    log("polling started", apiBase());
    refreshDashboard({ force: true });
    pollTimer = setInterval(() => {
      refreshDashboard({ force: false });
    }, POLL_MS);
  }

  function onNavigate(targetId) {
    if (targetId === "page-data") {
      log("Data page opened — immediate refresh");
      refreshDashboard({ force: true });
    }
  }

  window.plantAnalytics = {
    refresh: (opts) => refreshDashboard({ force: true, ...(opts || {}) }),
    onNavigate,
    getLastRefreshAt: () => lastRefreshAt,
    start: startPolling,
    stop: function () {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", startPolling);
  } else {
    startPolling();
  }
})();
