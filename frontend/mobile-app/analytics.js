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

  // Phase 3 — scan history filter state + last fetched rich payload (used by
  // the detail modal so it can fall back to in-memory data when the row's
  // canonical UUID isn't available in demo/memory mode).
  let shZoneFilter = "";
  let shStatusFilter = "";
  let lastRichScans = [];
  // Phase 3 correction — dedicated Scan History page state. Filters here are
  // independent from the Data-page scan history widget so users can drill in
  // without losing context.
  let histZoneFilter = "";
  let histStatusFilter = "";
  let histScans = [];
  let histInFlight = false;

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
    if (status === "UNKNOWN") return "et-unk";
    return "et-warn";
  }

  // --- Phase 3 polish — friendly fallbacks for missing/legacy data ---------
  const _UNCLASSIFIED = new Set(["", "unknown", "pending", "pending analysis", "unclassified", "n/a"]);

  function _isUnclassified(scan) {
    // Disease-string driven. A valid prediction like "Diseased" stays
    // classified even at modest confidence; the confidence column itself
    // tells the story. We only treat truly empty / "Unknown" rows as
    // unclassified — matches backend _status_from in routes/scans.py.
    if (!scan) return true;
    const d = (scan.disease || "").trim().toLowerCase();
    return !d || _UNCLASSIFIED.has(d);
  }

  function _friendlyDisease(scan) {
    if (_isUnclassified(scan)) {
      return scan && scan.is_legacy ? "Unclassified scan" : "Pending analysis";
    }
    return scan.disease;
  }

  function _friendlyPlantName(scan) {
    if (!scan) return "Plant specimen";
    return scan.plant_name || (scan.plant_id ? "Cucumber" : "Plant specimen");
  }

  function _friendlyConfidence(scan) {
    if (_isUnclassified(scan)) return "—";
    return ((scan.confidence || 0) * 100).toFixed(1) + "%";
  }

  function _friendlyStatusLabel(status) {
    if (status === "UNKNOWN") return "Unclassified";
    if (status === "PASS") return "Healthy";
    if (status === "WARN") return "Warning";
    if (status === "CRITICAL") return "Critical";
    return status || "Warning";
  }

  function _scanLegacyBadge(scan) {
    if (!scan) return "";
    if (scan.is_legacy) return "Legacy scan record";
    if (_isUnclassified(scan)) return "Missing prediction metadata";
    return "";
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

  function _isHttpUrl(s) {
    return typeof s === "string" && /^https?:\/\//i.test(s);
  }

  function _resolveThumb(scan) {
    const base = window.PLANT_API_BASE || "";
    const meta = scan && scan.metadata ? scan.metadata : {};
    const url = scan.image_url || meta.image_url || null;
    if (url) return _isHttpUrl(url) ? url : `${base}${url.startsWith("/") ? "" : "/"}${url}`;
    const path = scan.image_path || meta.saved_path || null;
    if (!path) return null;
    const norm = (path[0] === "/" ? path : "/" + path).replace(/\\/g, "/");
    return `${base}${norm}`;
  }

  /** Clean PlantVision thumbnail block. Falls back to an SVG placeholder
   *  (a stylized leaf) when no persisted image exists — never shows the
   *  green-checkerboard healthy_leaf.png placeholder again. */
  function _renderThumb(scan) {
    const thumbUrl = _resolveThumb(scan);
    const statusKey = (scan && scan.status || "WARN").toLowerCase();
    const thumbCls = `sh-thumb sh-status-${statusKey}`;
    if (thumbUrl) {
      return `<span class="${thumbCls}"><img src="${thumbUrl}" alt="" loading="lazy" onerror="this.parentNode.classList.add('sh-thumb-placeholder');this.remove()"></span>`;
    }
    return `<span class="${thumbCls} sh-thumb-placeholder" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 4 13V4h9a7 7 0 0 1 7 7v9z"/><path d="M4 4l16 16"/></svg></span>`;
  }

  function _scanTs(scan) {
    // Rich rows expose ISO created_at; legacy memory rows expose epoch ts.
    if (scan && scan.created_at) {
      const t = Date.parse(scan.created_at);
      return Number.isNaN(t) ? null : Math.floor(t / 1000);
    }
    return typeof scan.timestamp === "number" ? scan.timestamp : null;
  }

  function _scanLabel(scan) {
    const disease = _friendlyDisease(scan);
    const plant = scan && (scan.plant_name || scan.plant_id);
    return plant ? `${disease} · ${plant}` : disease;
  }

  function _scanSubLine(scan) {
    const legacy = _scanLegacyBadge(scan);
    if (legacy) return legacy;
    const bits = [];
    if (scan.id) bits.push(String(scan.id).slice(0, 8));
    if (scan.device_id) bits.push(scan.device_id);
    if (scan.scan_source) bits.push(scan.scan_source);
    return bits.join(" · ") || "—";
  }

  function renderScanHistory(rows, source, isLive) {
    const body = document.getElementById("scan-table-body");
    const tag = document.getElementById("scan-history-tag");
    const srcEl = document.getElementById("sh-source");
    if (!body) return;
    if (tag) tag.textContent = rows.length ? `Recent ${rows.length}` : "Recent";
    if (srcEl) {
      const labelMap = { postgres: "● Supabase Cloud", memory: "● Memory fallback", demo: "○ No persisted scans" };
      srcEl.textContent = labelMap[source] || "";
    }

    if (!rows.length) {
      const msg = (shZoneFilter || shStatusFilter)
        ? "No scans match the current filter."
        : (isLive ? "No scans yet — run a scan from Home." : "No scans yet. Demo metrics shown until first scan.");
      body.innerHTML = `<div class="scan-table-empty">${msg}</div>`;
      return;
    }

    const html = rows
      .map((r) => {
        const cls = statusTagClass(r.status);
        const conf = _friendlyConfidence(r);
        const ts = _scanTs(r);
        const time = ts != null ? fmtAgo(ts) : "—";
        const zoneTxt = zoneLabel(r.zone_id || "");
        const thumb = _renderThumb(r);
        const health = (typeof r.health_score === "number" && !_isUnclassified(r))
          ? `<span class="sh-health"><span class="sh-health-bar" style="--w:${Math.max(0, Math.min(100, r.health_score))}%"></span>${r.health_score}</span>`
          : `<span class="sh-health">—</span>`;
        return `<div class="scan-table-row sh-row" data-scan-id="${r.id || ""}" data-scan-zone="${r.zone_id || ""}" tabindex="0" role="button" aria-label="Open scan detail">
          ${thumb}
          <span class="sh-detail">
            <span class="sh-detail-name">${_scanLabel(r)}</span>
            <span class="sh-detail-sub mono">${_scanSubLine(r)}</span>
          </span>
          <span class="sh-zone mono">${zoneTxt}</span>
          <span class="entry-tag ${cls} col-status">${_friendlyStatusLabel(r.status)}</span>
          <span class="sh-conf mono">${conf}</span>
          ${health}
          <span class="sh-time mono">${time}</span>
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
        const thumbUrl = _resolveThumb(r);
        const ts = _scanTs(r);
        const time = ts != null ? fmtAgo(ts) : "—";
        const shortId = r.id ? String(r.id).slice(0, 8) : (r.scan_id || "");
        const disease = _friendlyDisease(r);
        const conf = _friendlyConfidence(r);
        const thumbInner = thumbUrl
          ? `<img src="${thumbUrl}" alt="" class="entry-img" loading="lazy" onerror="this.parentNode.classList.add('entry-thumb-placeholder');this.remove()">`
          : `<svg class="entry-img-svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 4 13V4h9a7 7 0 0 1 7 7v9z"/><path d="M4 4l16 16"/></svg>`;
        return `<article class="entry" data-scan-id="${r.id || r.scan_id || ""}">
          <div class="entry-thumb ${thumbCls}${thumbUrl ? "" : " entry-thumb-placeholder"}">${thumbInner}</div>
          <div class="entry-body">
            <div class="entry-r1">
              <span class="entry-name">${disease}</span>
              <span class="entry-tag ${cls}">${_friendlyStatusLabel(r.status)}</span>
            </div>
            <span class="entry-sub mono">${time} · ${conf} · ${shortId}</span>
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
      // Final polish — contextual empty value instead of a bare em-dash.
      const _miss = "<i class='zh-miss'>No reading</i>";
      const temp = z.air_temperature != null ? z.air_temperature.toFixed(1) + "°C" : _miss;
      const hum = z.air_humidity != null ? z.air_humidity.toFixed(0) + "%" : _miss;
      const ph = z.soil_ph != null ? z.soil_ph.toFixed(1) : _miss;
      const ec = z.soil_ec != null ? z.soil_ec.toFixed(1) : _miss;
      const texts = [`Temp: ${temp}`, `Humid: ${hum}`, `pH: ${ph}`, `EC: ${ec}`];
      metrics.querySelectorAll("span").forEach((sp, i) => {
        if (texts[i] && sp.innerHTML !== texts[i]) sp.innerHTML = texts[i];
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

      const scanQs = new URLSearchParams();
      scanQs.set("limit", "50");
      if (shZoneFilter)   scanQs.set("zone", shZoneFilter);
      if (shStatusFilter) scanQs.set("status", shStatusFilter);

      const [sumRes, scanRes, evRes, zoneRes, insRes, homeScanRes] = await Promise.all([
        fetchJson("/analytics/summary"),
        fetchJson(`/scans/history?${scanQs.toString()}`),
        fetchJson("/analytics/events?limit=25"),
        fetchJson("/analytics/zones"),
        fetchJson("/analytics/insights"),
        // Unfiltered top-N for the Home "Recent activity" tile.
        fetchJson("/scans/history?limit=5"),
      ]);
      const histRes = scanRes;

      const anyOk =
        sumRes.ok || histRes.ok || evRes.ok || zoneRes.ok || insRes.ok;
      if (!anyOk) {
        showApiError("backend unreachable");
        return;
      }

      let summary = sumRes.ok ? sumRes.data : null;
      const richHistory = histRes.ok ? histRes.data : null; // { source, scans:[...] }
      const homeHistory = homeScanRes.ok ? homeScanRes.data : null;
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
        history: richHistory && (richHistory.scans || []).length,
      });

      if (summary) renderSummary(summary);
      if (richHistory) {
        const scans = Array.isArray(richHistory.scans) ? richHistory.scans : [];
        lastRichScans = scans;
        const histKey = stableStringify({ src: richHistory.source, scans });
        if (force || lastSnapshot.history !== histKey) {
          lastSnapshot.history = histKey;
          renderScanHistory(scans, richHistory.source || "demo", isLive);
        }
      }
      if (homeHistory) {
        const homeScans = Array.isArray(homeHistory.scans) ? homeHistory.scans : [];
        renderHomeLog(homeScans);
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
    if (targetId === "page-history") {
      bindHistoryPage();
      refreshHistoryPage();
    }
  }

  // -------------------- Phase 3 — scan history interactions ---------------

  function _envVal(v, suffix) {
    if (v == null || v === "") return "—";
    return `${v}${suffix || ""}`;
  }

  function _renderDetailFromScan(scan) {
    if (!scan) return;
    const setText = (id, v) => { const el = document.getElementById(id); if (el) el.textContent = v; };
    const meta = scan.metadata || {};
    const snap = scan.sensor_snapshot || meta.sensor_snapshot || null;
    const conf = ((scan.confidence || 0) * 100).toFixed(1);
    const ts   = _scanTs(scan);

    setText("sd-title", _friendlyDisease(scan));
    const subParts = [];
    if (scan.id) subParts.push("#" + String(scan.id).slice(0, 8));
    if (scan.zone_id) subParts.push(zoneLabel(scan.zone_id));
    if (ts != null) subParts.push(fmtAgo(ts));
    if (scan.is_legacy) subParts.push("legacy scan");
    setText("sd-sub", subParts.join(" · ") || "—");

    // Image / thumbnail
    const thumbEl = document.getElementById("sd-thumb");
    const emptyEl = document.getElementById("sd-thumb-empty");
    const url = _resolveThumb(scan);
    if (thumbEl) {
      if (url) {
        thumbEl.src = url;
        thumbEl.removeAttribute("hidden");
        thumbEl.onerror = () => {
          thumbEl.setAttribute("hidden", "");
          if (emptyEl) { emptyEl.textContent = "Image unavailable"; emptyEl.style.display = ""; }
        };
        if (emptyEl) emptyEl.style.display = "none";
      } else {
        thumbEl.setAttribute("hidden", "");
        if (emptyEl) { emptyEl.textContent = "No image stored for this scan"; emptyEl.style.display = ""; }
      }
    }

    // Meta chips (zone, device, source, plant_id)
    const metaGrid = document.getElementById("sd-meta-grid");
    if (metaGrid) {
      const chips = [];
      const chip = (lbl, val) => `<span class="sd-meta-chip"><span class="sd-chip-lbl">${lbl}</span><strong>${val}</strong></span>`;
      chips.push(chip("Zone", zoneLabel(scan.zone_id || "")));
      if (scan.device_id) chips.push(chip("Device", scan.device_id));
      if (scan.scan_source) chips.push(chip("Source", scan.scan_source));
      const pid = scan.plant_id || meta.plant_id;
      if (pid) chips.push(chip("Plant", pid));
      const pname = scan.plant_name || meta.plant_name;
      if (pname) chips.push(chip("Type", pname));
      if (scan.model_name) chips.push(chip("Model", scan.model_name));
      metaGrid.innerHTML = chips.join("");
    }

    // Diagnosis metric cards
    const metricsEl = document.getElementById("sd-metrics");
    if (metricsEl) {
      const cards = [];
      const card = (lbl, val, mono) => `<div class="sd-metric"><span class="sd-metric-lbl">${lbl}</span><span class="sd-metric-val${mono ? " sd-mono" : ""}">${val}</span></div>`;
      const unclassified = _isUnclassified(scan);
      cards.push(card("Confidence", _friendlyConfidence(scan), true));
      cards.push(card("Health Score", (!unclassified && scan.health_score != null) ? scan.health_score + "%" : "—", true));
      cards.push(card("Risk Level", (!unclassified && scan.risk_level) || "—"));
      cards.push(card("Env. Stress", (scan.environment_stress || (meta && meta.environment_stress)) || "—"));
      cards.push(card("Survival", (!unclassified && scan.survival_score != null) ? scan.survival_score + "%" : "—", true));
      metricsEl.innerHTML = cards.join("");
    }

    setText("sd-rec", scan.recommendation || meta.recommendation || "No advisory generated for this scan.");

    // Sensor snapshot or safe fallback
    const snapEl = document.getElementById("sd-snapshot");
    if (snapEl) {
      if (snap && typeof snap === "object") {
        const snapCards = [
          ["Air Temp",    snap.air_temperature,   "°C"],
          ["Air Humidity", snap.air_humidity,     "%"],
          ["Light",       snap.light_lux,         " lx"],
          ["Soil Temp",   snap.soil_temperature,  "°C"],
          ["Soil Hum.",   snap.soil_humidity,     "%"],
          ["Soil pH",     snap.soil_ph,           ""],
          ["Soil EC",     snap.soil_ec,           " mS/cm"],
        ].map(([lbl, val, suf]) => `<div class="sd-snap-card"><span class="sd-snap-lbl">${lbl}</span><span class="sd-snap-val">${_envVal(val, suf)}</span></div>`).join("");
        snapEl.innerHTML = snapCards;
      } else {
        snapEl.innerHTML = `<div class="sd-snap-empty">No sensor snapshot available for this scan.</div>`;
      }
    }
  }

  async function openScanDetail(scanId, zoneIdHint) {
    const modal = document.getElementById("sd-modal");
    if (!modal) return;
    modal.classList.add("active");
    let scan = null;
    // Prefer canonical DB record (richer than in-memory fallback)
    if (scanId && typeof fetchScanDetail === "function") {
      try { scan = await fetchScanDetail(scanId); } catch (_) { scan = null; }
    }
    if (!scan) {
      // Fall back to the row we already have (in-memory mode)
      scan = lastRichScans.find((s) => s.id === scanId || s.scan_id === scanId) || null;
    }
    if (!scan && zoneIdHint) {
      scan = lastRichScans.find((s) => s.zone_id === zoneIdHint) || null;
    }
    _renderDetailFromScan(scan || { disease: "Scan unavailable", confidence: 0 });
  }

  function closeScanDetail() {
    const m = document.getElementById("sd-modal");
    if (m) m.classList.remove("active");
  }

  // -------------------- Phase 3 — dedicated Scan History page ------------

  function _statusCardCls(s) {
    if (s === "PASS") return "hist-st-ok";
    if (s === "CRITICAL") return "hist-st-crit";
    if (s === "UNKNOWN") return "hist-st-unk";
    return "hist-st-warn";
  }

  function renderHistoryGrid(scans, source) {
    const grid = document.getElementById("hist-grid");
    const empty = document.getElementById("hist-empty");
    const totalEl = document.getElementById("hist-total");
    const liveEl = document.getElementById("hist-live-tag");
    if (!grid) return;

    if (liveEl) {
      const labels = {
        postgres: "● Supabase Cloud",
        memory: "● Memory fallback",
        demo: "○ Demo",
      };
      liveEl.textContent = labels[source] || "● Live";
      liveEl.style.color = source === "postgres" ? "var(--sage)" : (source === "memory" ? "var(--gold)" : "var(--t4)");
    }

    if (!scans.length) {
      grid.innerHTML = "";
      grid.hidden = true;
      if (empty) empty.hidden = false;
      if (totalEl) totalEl.textContent = "0 scans";
      return;
    }

    if (empty) empty.hidden = true;
    grid.hidden = false;
    if (totalEl) totalEl.textContent = scans.length + (scans.length === 1 ? " scan" : " scans");

    const html = scans.map((r) => {
      const thumbUrl = _resolveThumb(r);
      const stCls = _statusCardCls(r.status);
      const stLabel = _friendlyStatusLabel(r.status);
      const ts = _scanTs(r);
      const time = ts != null ? fmtAgo(ts) : "—";
      const title = _friendlyDisease(r);
      // Final polish — keep card subtitles consistent. Show
      // "Zone · Device" when present, otherwise a subtle "Legacy scan" tag.
      const baseSub = `${r.zone_id ? zoneLabel(r.zone_id) + " · " : ""}${r.device_id || ""}`.replace(/ · $/, "").trim();
      const legacyTag = r.is_legacy ? `<span class="hist-card-sub-legacy">Legacy scan</span>` : "";
      const sub = baseSub
        ? `${baseSub}${legacyTag ? " · " + legacyTag : ""}`
        : (legacyTag || "—");
      const imgBlock = thumbUrl
        ? `<img src="${thumbUrl}" alt="" loading="lazy" onerror="this.parentNode.classList.add('placeholder');this.remove()">`
        : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 4 13V4h9a7 7 0 0 1 7 7v9z"/><path d="M4 4l16 16"/></svg>`;
      const imgCls = thumbUrl ? "hist-card-img" : "hist-card-img placeholder";
      const conf = _friendlyConfidence(r);
      const health = (typeof r.health_score === "number" && !_isUnclassified(r)) ? r.health_score + "%" : "—";
      const chips = [];
      if (r.plant_id)   chips.push(`<span class="hist-card-chip hist-chip-plant">${r.plant_id}</span>`);
      if (r.scan_source) chips.push(`<span class="hist-card-chip">${r.scan_source}</span>`);
      if (r.has_sensor_snapshot) chips.push(`<span class="hist-card-chip">+ sensors</span>`);

      return `<article class="hist-card" data-scan-id="${r.id || ""}" data-scan-zone="${r.zone_id || ""}" tabindex="0" role="button" aria-label="Open scan detail">
        <div class="${imgCls}">
          ${imgBlock}
          <span class="hist-status ${stCls}">${stLabel}</span>
          <span class="hist-time">${time}</span>
        </div>
        <div class="hist-card-body">
          <div>
            <div class="hist-card-title">${title}</div>
            <div class="hist-card-sub">${sub || "—"}</div>
          </div>
          ${chips.length ? `<div class="hist-card-meta">${chips.join("")}</div>` : ""}
          <div class="hist-card-stats">
            <div class="hist-card-stat"><span class="hist-card-stat-lbl">Confidence</span><span class="hist-card-stat-val">${conf}</span></div>
            <div class="hist-card-stat"><span class="hist-card-stat-lbl">Health</span><span class="hist-card-stat-val">${health}</span></div>
            <div class="hist-card-stat"><span class="hist-card-stat-lbl">Zone</span><span class="hist-card-stat-val">${zoneLabel(r.zone_id || "")}</span></div>
          </div>
        </div>
      </article>`;
    }).join("");

    grid.innerHTML = html;
  }

  async function refreshHistoryPage() {
    if (histInFlight) return;
    histInFlight = true;
    try {
      const qs = new URLSearchParams();
      qs.set("limit", "100");
      if (histZoneFilter) qs.set("zone", histZoneFilter);
      if (histStatusFilter) qs.set("status", histStatusFilter);
      const res = await fetchJson(`/scans/history?${qs.toString()}`);
      if (res.ok && res.data) {
        const scans = Array.isArray(res.data.scans) ? res.data.scans : [];
        histScans = scans;
        renderHistoryGrid(scans, res.data.source || "demo");
      } else {
        renderHistoryGrid([], "demo");
      }
    } finally {
      histInFlight = false;
    }
  }

  function bindHistoryPage() {
    const zSel = document.getElementById("hist-zone-filter");
    const sSel = document.getElementById("hist-status-filter");
    const reset = document.getElementById("hist-reset");
    const refresh = document.getElementById("hist-refresh");
    const grid = document.getElementById("hist-grid");

    if (zSel && !zSel.dataset.bound) {
      zSel.addEventListener("change", () => {
        histZoneFilter = zSel.value || "";
        refreshHistoryPage();
      });
      zSel.dataset.bound = "1";
    }
    if (sSel && !sSel.dataset.bound) {
      sSel.addEventListener("change", () => {
        histStatusFilter = sSel.value || "";
        refreshHistoryPage();
      });
      sSel.dataset.bound = "1";
    }
    if (reset && !reset.dataset.bound) {
      reset.addEventListener("click", () => {
        histZoneFilter = ""; histStatusFilter = "";
        if (zSel) zSel.value = "";
        if (sSel) sSel.value = "";
        refreshHistoryPage();
      });
      reset.dataset.bound = "1";
    }
    if (refresh && !refresh.dataset.bound) {
      refresh.addEventListener("click", () => refreshHistoryPage());
      refresh.dataset.bound = "1";
    }
    if (grid && !grid.dataset.bound) {
      const handleOpen = (target) => {
        const card = target.closest(".hist-card");
        if (!card) return;
        openScanDetail(card.getAttribute("data-scan-id") || "", card.getAttribute("data-scan-zone") || "");
      };
      grid.addEventListener("click", (e) => handleOpen(e.target));
      grid.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handleOpen(e.target); }
      });
      grid.dataset.bound = "1";
    }
  }

  function bindScanHistoryUI() {
    // Filter selects
    const zSel = document.getElementById("sh-zone-filter");
    const sSel = document.getElementById("sh-status-filter");
    if (zSel && !zSel.dataset.bound) {
      zSel.addEventListener("change", () => {
        shZoneFilter = zSel.value || "";
        lastSnapshot.history = ""; // force re-render
        refreshDashboard({ force: true });
      });
      zSel.dataset.bound = "1";
    }
    if (sSel && !sSel.dataset.bound) {
      sSel.addEventListener("change", () => {
        shStatusFilter = sSel.value || "";
        lastSnapshot.history = "";
        refreshDashboard({ force: true });
      });
      sSel.dataset.bound = "1";
    }

    // Row click → open detail
    const body = document.getElementById("scan-table-body");
    if (body && !body.dataset.bound) {
      body.addEventListener("click", (e) => {
        const row = e.target.closest(".sh-row");
        if (!row) return;
        const id = row.getAttribute("data-scan-id") || "";
        const zone = row.getAttribute("data-scan-zone") || "";
        openScanDetail(id, zone);
      });
      body.addEventListener("keydown", (e) => {
        if (e.key !== "Enter" && e.key !== " ") return;
        const row = e.target.closest(".sh-row");
        if (!row) return;
        e.preventDefault();
        const id = row.getAttribute("data-scan-id") || "";
        const zone = row.getAttribute("data-scan-zone") || "";
        openScanDetail(id, zone);
      });
      body.dataset.bound = "1";
    }

    // Close detail (backdrop + close button)
    const modal = document.getElementById("sd-modal");
    const closeBtn = document.getElementById("sd-close");
    if (closeBtn && !closeBtn.dataset.bound) {
      closeBtn.addEventListener("click", closeScanDetail);
      closeBtn.dataset.bound = "1";
    }
    if (modal && !modal.dataset.bound) {
      modal.addEventListener("click", (e) => {
        if (e.target === modal) closeScanDetail();
      });
      window.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && modal.classList.contains("active")) closeScanDetail();
      });
      modal.dataset.bound = "1";
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => { bindScanHistoryUI(); bindHistoryPage(); });
  } else {
    bindScanHistoryUI();
    bindHistoryPage();
  }
  // Re-bind after a scan completes (in case the dashboard re-renders empty state).
  window.addEventListener("plantvision:scan-complete", () => {
    bindScanHistoryUI();
    refreshDashboard({ force: true });
    // Refresh the dedicated history page in background so it's ready next visit.
    refreshHistoryPage();
  });

  window.plantAnalytics = {
    refresh: (opts) => refreshDashboard({ force: true, ...(opts || {}) }),
    openScanDetail,
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
