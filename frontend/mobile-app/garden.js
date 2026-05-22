/**
 * PlantVision Garden Map — live command center (polls /analytics/garden).
 */
(function () {
  const POLL_MS = 5000;
  const LOCAL_ZONE_MAP = {
    a: "zone_alpha",
    b: "zone_beta",
    c: "zone_gamma",
    d: "zone_delta",
  };

  let pollTimer = null;
  let dashboard = null;
  let selectedZoneKey = null;
  let searchQuery = "";
  let lastSnapshot = "";
  let lastAlertKey = "";
  let deviceCardEls = new Map();
  let alertEls = new Map();
  let markerEls = new Map();
  let expandedDevice = null;
  let lastDataRefresh = 0;
  const counterAnim = new Map();
  let isSimulation = false;
  const scanByZone = {};
  // Phase 3: per-zone persisted scan counts (refreshed from /scans/zone-counts).
  const zoneScanCounts = {};
  let zoneScanCountsAt = 0;

  const ZONE_ALIAS = {
    a: ["alpha", "zone_alpha", "zone alpha"],
    b: ["beta", "zone_beta", "zone beta"],
    c: ["gamma", "zone_gamma", "zone gamma"],
    d: ["delta", "zone_delta", "zone delta"],
  };

  const STATUS_SEARCH = {
    healthy: ["healthy", "ok", "pass", "nominal"],
    warn: ["warning", "warn", "at risk", "risk", "stale"],
    crit: ["critical", "crit", "disease", "alert"],
    off: ["offline", "off", "awaiting", "no sensor"],
  };

  function bridge() {
    return window.plantGardenBridge || {};
  }

  function stableStringify(v) {
    try {
      return JSON.stringify(v);
    } catch (_) {
      return "";
    }
  }

  function fmtAgo(ts) {
    if (!ts) return "never";
    const sec = Math.max(0, Math.floor(Date.now() / 1000 - ts));
    if (sec < 60) return sec + "s ago";
    if (sec < 3600) return Math.floor(sec / 60) + "m ago";
    return Math.floor(sec / 3600) + "h ago";
  }

  function fmtTime(ts) {
    return new Date(ts * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function localZoneId(z) {
    return z.zone_id || LOCAL_ZONE_MAP[z.id] || z.id;
  }

  function mapStatus(st) {
    if (st === "HEALTHY") return "Healthy";
    if (st === "WARNING") return "At Risk";
    if (st === "CRITICAL") return "Critical";
    return "Offline";
  }

  function statusClass(st) {
    const s = mapStatus(st);
    if (s === "Healthy") return "ok";
    if (s === "At Risk") return "warn";
    if (s === "Critical") return "crit";
    return "off";
  }

  function zoneBackend(localZone) {
    if (!dashboard || !dashboard.zones) return null;
    const zid = localZoneId(localZone);
    return dashboard.zones.find((z) => z.zone_id === zid) || null;
  }

  function animateCounter(el, target) {
    if (!el) return;
    const from = parseInt(el.dataset.value || el.textContent, 10) || 0;
    const t = Math.max(0, Math.floor(target));
    if (from === t) {
      el.textContent = String(t);
      el.dataset.value = String(t);
      return;
    }
    if (counterAnim.has(el)) cancelAnimationFrame(counterAnim.get(el));
    const start = performance.now();
    const dur = 420;
    const step = (now) => {
      const p = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      const val = Math.round(from + (t - from) * eased);
      el.textContent = String(val);
      if (p < 1) counterAnim.set(el, requestAnimationFrame(step));
      else {
        el.textContent = String(t);
        el.dataset.value = String(t);
        counterAnim.delete(el);
        el.classList.add("garden-count-pulse");
        setTimeout(() => el.classList.remove("garden-count-pulse"), 450);
      }
    };
    counterAnim.set(el, requestAnimationFrame(step));
  }

  function simulatedSummaryFromZones() {
    const zones = dashboard?.zones || [];
    if (zones.length) {
      return {
        healthy: zones.filter((z) => z.status === "HEALTHY").length,
        warning: zones.filter((z) => z.status === "WARNING").length,
        critical: zones.filter((z) => z.status === "CRITICAL").length,
        offline_devices: (dashboard?.devices || []).filter((d) => d.freshness === "offline").length,
        simulated: true,
      };
    }
    return { healthy: 2, warning: 1, critical: 1, offline_devices: 0, simulated: true };
  }

  function resolveSummaryCounts(s) {
    const live = {
      healthy: s.healthy || 0,
      warning: s.warning || 0,
      critical: s.critical || 0,
      offline_devices: s.offline_devices || 0,
    };
    const total = live.healthy + live.warning + live.critical + live.offline_devices;
    if (!isSimulation || total > 0) return { ...live, simulated: false };
    return simulatedSummaryFromZones();
  }

  function updateSummaryCards(counts) {
    document.querySelectorAll(".garden-sum-card").forEach((card) => {
      const id = card.querySelector(".garden-sum-val")?.id;
      let val = 0;
      if (id === "garden-sum-healthy") val = counts.healthy || 0;
      else if (id === "garden-sum-warn") val = counts.warning || 0;
      else if (id === "garden-sum-crit") val = counts.critical || 0;
      else if (id === "garden-sum-offline") val = counts.offline_devices || 0;
      card.classList.toggle("garden-sum-zero", val === 0 && !counts.simulated);
      card.classList.toggle("garden-sum-simulated", !!counts.simulated);
    });
    const row = document.querySelector(".garden-summary-row");
    if (row) row.classList.toggle("garden-sim-active", !!counts.simulated);
  }

  function zoneSearchBlob(z, backend) {
    const zid = localZoneId(z);
    const st = backend ? mapStatus(backend.status) : z.status || "Offline";
    const cls = statusClass(backend?.status || "OFFLINE");
    const aliases = ZONE_ALIAS[z.id] || [];
    const parts = [
      z.id,
      z.name,
      zid,
      st,
      cls,
      backend?.status_note || "",
      ...aliases,
      ...(z.devices || []).map((d) => `${d.name || ""} ${d.ip || ""}`),
    ];
    Object.values(STATUS_SEARCH).forEach((words) => parts.push(...words));
    return parts.join(" ").toLowerCase();
  }

  function matchesSearch(blob, q) {
    if (!q) return true;
    if (blob.includes(q)) return true;
    if (q.includes("zone ") && blob.includes(q.replace("zone ", ""))) return true;
    for (const [cls, words] of Object.entries(STATUS_SEARCH)) {
      if (words.some((w) => q.includes(w)) && blob.includes(cls === "warn" ? "warn" : cls))
        return true;
      if (words.some((w) => q.includes(w)) && words.some((w) => blob.includes(w))) return true;
    }
    return false;
  }

  function indexScansFromHistory(history) {
    Object.keys(scanByZone).forEach((k) => delete scanByZone[k]);
    (history || []).forEach((s) => {
      const zid = s.zone_id;
      if (!zid) return;
      if (!scanByZone[zid] || s.timestamp > scanByZone[zid].timestamp) scanByZone[zid] = s;
    });
  }

  function gardenEmptyHtml(icon, title, hint, extraClass) {
    const cls = extraClass ? " " + extraClass : "";
    return (
      '<div class="garden-empty-state' +
      cls +
      '"><span class="garden-empty-icon" aria-hidden="true">' +
      icon +
      '</span><span class="garden-empty-pulse" aria-hidden="true"></span><p class="garden-empty-title">' +
      title +
      '</p><span class="garden-empty-hint">' +
      hint +
      "</span></div>"
    );
  }

  function buildZoneTooltip(z, backend) {
    const zid = localZoneId(z);
    const st = mapStatus(backend?.status || "OFFLINE");
    const cls = statusClass(backend?.status || "OFFLINE");
    const scan = scanByZone[zid];
    const zoneDevs = (dashboard?.devices || []).filter((d) => d.zone_id === zid);
    let sensorLabel = "Offline";
    if (zoneDevs.some((d) => d.freshness === "live")) sensorLabel = "Live";
    else if (zoneDevs.some((d) => d.freshness === "stale")) sensorLabel = "Stale";
    const lines = [
      '<div class="zt-title">' + z.name + "</div>",
      '<span class="zt-status zts-' + cls + '">' + st + "</span>",
    ];
    if (backend && backend.air_temperature != null) {
      lines.push(
        '<div class="zt-row">Temp <b>' +
        backend.air_temperature.toFixed(1) +
        "°C</b> · Hum <b>" +
        Math.round(backend.air_humidity) +
        "%</b></div>"
      );
    }
    if (scan) {
      lines.push(
        '<div class="zt-row">Last scan: <b>' +
        scan.disease +
        "</b> (" +
        (scan.confidence * 100).toFixed(0) +
        "%)</div>"
      );
    } else {
      lines.push('<div class="zt-row zt-muted">Last scan: —</div>');
    }
    const totalScans = zoneScanCounts[zid] || 0;
    if (totalScans > 0) {
      lines.push('<div class="zt-row zt-muted">Scans: <b>' + totalScans + '</b></div>');
    }
    lines.push('<div class="zt-row">Sensor: <b>' + sensorLabel + "</b></div>");
    if (isSimulation) lines.push('<div class="zt-sim">Simulation preview</div>');
    return lines.join("");
  }

  function devicePreview(reading) {
    if (!reading) {
      return {
        health: "Awaiting",
        healthCls: "off",
        insight: "Awaiting live sensor stream",
        insightTone: "off",
      };
    }
    const insights = reading.insights || [];
    const pick =
      insights.find((i) => i.tone === "crit") ||
      insights.find((i) => i.tone === "warn") ||
      insights[0];
    const st = (reading.status || "").toUpperCase();
    let health = "Monitoring";
    let healthCls = "ok";
    if (reading.freshness === "offline" || st === "OFFLINE") {
      health = "Offline";
      healthCls = "off";
    } else if (st === "CRITICAL") {
      health = "Critical";
      healthCls = "crit";
    } else if (st === "WARNING") {
      health = "Warning";
      healthCls = "warn";
    } else if (st === "HEALTHY") {
      health = "Healthy";
      healthCls = "ok";
    }
    return {
      health,
      healthCls,
      insight: pick?.label || (healthCls === "ok" ? "All sensors nominal" : "Monitoring"),
      insightTone: pick?.tone || (healthCls === "ok" ? "pass" : "warn"),
    };
  }

  function alertCategory(a) {
    const msg = (a.message || "").toLowerCase();
    const et = (a.event_type || "").toLowerCase();
    if (
      et === "device" ||
      et === "sensor" ||
      et === "connection" ||
      msg.includes("connect") ||
      msg.includes("stream") ||
      msg.includes("esp32")
    )
      return "sys";
    if (
      et === "alert" ||
      msg.includes("critical") ||
      msg.includes("disease") ||
      a.severity === "crit"
    )
      return "crit";
    if (et === "scan" && (msg.includes("disease") || msg.includes("critical")))
      return "crit";
    if (msg.includes("warning") || msg.includes("risk") || a.severity === "warn")
      return "warn";
    if (et === "scan") return "info";
    return "info";
  }

  function flashZoneMarker(zoneKey) {
    const b = bridge();
    const zones = b.getZones?.() || [];
    // Accept either the local short id ("a") OR the backend slug ("zone_alpha")
    const targetSlug = LOCAL_ZONE_MAP[zoneKey] || zoneKey;
    const z = zones.find((x) =>
      localZoneId(x) === zoneKey || localZoneId(x) === Object.keys(LOCAL_ZONE_MAP).find((k) => LOCAL_ZONE_MAP[k] === targetSlug)
    );
    if (!z) return;
    const m = b.getMarkers?.()?.[z.id];
    const inner = m?.getElement?.()?.querySelector(".zone-marker");
    if (inner) {
      inner.classList.add("zm-flash");
      setTimeout(() => inner.classList.remove("zm-flash"), 3200);
    }
  }

  function drawSparkline(canvas, values) {
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    const dpr = window.devicePixelRatio || 1;
    const cw = canvas.clientWidth || 72;
    const ch = canvas.clientHeight || 22;
    canvas.width = cw * dpr;
    canvas.height = ch * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    if (!values || values.length < 2) {
      ctx.strokeStyle = "rgba(140,168,140,0.12)";
      ctx.setLineDash([2, 2]);
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
    ctx.lineWidth = 1.4;
    ctx.setLineDash([]);
    ctx.stroke();
  }

  function deviceReading(localZone, device, idx) {
    const zid = localZoneId(localZone);
    if (!dashboard || !dashboard.devices) return null;
    const zoneDevs = dashboard.devices.filter((d) => d.zone_id === zid);
    if (!zoneDevs.length) return null;

    // 1) Prefer an exact match by device_id (e.g. esp32_001) — this is the
    //    authoritative identifier the backend uses.
    const wantedId = (device.device_id || "").toLowerCase();
    if (wantedId) {
      const exact = zoneDevs.find((d) => (d.device_id || "").toLowerCase() === wantedId);
      if (exact) return exact;
    }

    // 2) If the zone only has one device, that's it (single-sensor case).
    if (zoneDevs.length === 1) return zoneDevs[0];

    // 3) Fuzzy fallback by friendly name (legacy demo data uses "ESP32-A1").
    const friendly = (device.name || "").toLowerCase().replace(/[-_\s]/g, "");
    if (friendly) {
      const fuzzy = zoneDevs.find((d) =>
        (d.device_id || "").toLowerCase().replace(/[-_\s]/g, "").includes(friendly)
      );
      if (fuzzy) return fuzzy;
    }
    return zoneDevs[idx % zoneDevs.length] || zoneDevs[0];
  }

  function patchSummary() {
    if (!dashboard) return;
    const s = dashboard.summary || {};

    // Mode resolution — single source of truth via window.plantSensor.
    // garden source == "live" OR fresh sensor context wins.
    const sensorCtx = window.plantSensor && window.plantSensor.last ? window.plantSensor.last() : null;
    const sensorIsLive = sensorCtx && (sensorCtx.mode === "live" || sensorCtx.mode === "stale");
    const live = dashboard.source === "live" || sensorIsLive;
    isSimulation = !live;

    const counts = resolveSummaryCounts(s);
    animateCounter(document.getElementById("garden-sum-healthy"), counts.healthy);
    animateCounter(document.getElementById("garden-sum-warn"), counts.warning);
    animateCounter(document.getElementById("garden-sum-crit"), counts.critical);
    animateCounter(document.getElementById("garden-sum-offline"), counts.offline_devices);
    updateSummaryCards(counts);

    const tag = document.getElementById("garden-live-tag");
    const badge = document.getElementById("garden-mode-badge");
    const stale = sensorCtx && sensorCtx.mode === "stale";
    if (tag) {
      tag.textContent = stale ? "● Stale" : live ? "● Live" : "● Connected";
      tag.classList.toggle("garden-live-on", live && !stale);
      tag.classList.toggle("garden-live-sim", !live);
    }
    if (badge) {
      // Honest wording: only show "Simulation Mode" if there's no sensor
      // context at all; show "Stale Sensor" when a reading exists but old.
      if (stale) {
        badge.hidden = false;
        badge.textContent = "Stale Sensor";
      } else if (live) {
        badge.hidden = true;
        badge.textContent = "";
      } else {
        badge.hidden = false;
        badge.textContent = "Simulation Mode";
      }
    }
    const polled = document.getElementById("garden-polled-at");
    if (polled) polled.textContent = "Updated " + fmtTime(Math.floor(lastDataRefresh / 1000));
  }

  function createMarkerIcon(st, selected, dimmed) {
    const cls = statusClass(st);
    const extra = [
      selected ? "zm-selected zm-focus" : "",
      dimmed ? "zm-dimmed" : "",
    ].join(" ");
    return L.divIcon({
      className: "zone-marker-wrap",
      html: `<span class="zone-marker zm-${cls} ${extra}"><span class="zone-marker-ring"></span><span class="zone-marker-ripple zm-ripple-a"></span><span class="zone-marker-ripple zm-ripple-b"></span><span class="zone-marker-core"></span></span>`,
      iconSize: [40, 40],
      iconAnchor: [20, 20],
    });
  }

  function patchMarkers() {
    const b = bridge();
    const map = b.getMap?.();
    if (!map || typeof L === "undefined") return;
    const zones = b.getZones?.() || [];
    const markers = b.getMarkers?.() || {};

    zones.forEach((z) => {
      const zid = localZoneId(z);
      const backend = zoneBackend(z);
      const st = backend ? backend.status : "OFFLINE";
      if (backend) z.status = mapStatus(st);

      const blob = zoneSearchBlob(z, backend);
      const hidden = searchQuery && !matchesSearch(blob, searchQuery);

      const dimmed = selectedZoneKey && localZoneId(z) !== selectedZoneKey;
      const selected = selectedZoneKey === localZoneId(z);

      let marker = markers[z.id];
      const needsReplace =
        !marker ||
        (marker.getElement && !marker.getElement()?.querySelector?.(".zone-marker"));
      if (needsReplace) {
        if (marker) map.removeLayer(marker);
        const icon = createMarkerIcon(st, selected, dimmed);
        marker = L.marker([z.lat, z.lng], { icon, zIndexOffset: selected ? 1000 : 0 }).addTo(map);
        marker.on("click", (e) => {
          L.DomEvent.stopPropagation(e);
          selectZone(localZoneId(z));
        });
        markers[z.id] = marker;
        markerEls.set(z.id, marker);
      } else {
        marker.setIcon(createMarkerIcon(st, selected, dimmed));
        marker.setZIndexOffset(selected ? 1000 : 200);
        if (hidden) marker.setOpacity(0.15);
        else marker.setOpacity(dimmed ? 0.45 : 1);
      }

      marker.bindTooltip(buildZoneTooltip(z, backend), {
        className: "zone-marker-tip",
        direction: "top",
        offset: [0, -14],
        opacity: 1,
      });
    });
  }

  function selectZone(zoneKey) {
    selectedZoneKey = zoneKey;
    flashZoneMarker(zoneKey);
    try {
      window.dispatchEvent(new CustomEvent("plantvision:garden-zone-selected", {
        detail: { zone_id: zoneKey }
      }));
    } catch (_) { /* IE fallback not needed */ }
    // Phase 3 — populate the per-zone "Latest scans" panel
    refreshZoneScansPanel(zoneKey).catch(() => {});
    const b = bridge();
    const map = b.getMap?.();
    const zones = b.getZones?.() || [];
    const z = zones.find((x) => localZoneId(x) === zoneKey);
    if (z && map) {
      map.flyTo([z.lat, z.lng], 17, { duration: 0.7 });
    }
    const btn = document.getElementById("garden-show-all");
    if (btn) btn.hidden = !selectedZoneKey;
    patchMarkers();
    patchZoneChips();
    patchDevicePanel();
    patchAlerts();
    patchActivity();
  }

  function _gzsThumb(scan) {
    const base = window.PLANT_API_BASE || "";
    const url = scan.image_url || (scan.metadata && scan.metadata.image_url);
    if (url) {
      const norm = url.startsWith("http") ? url : `${base}${url.startsWith("/") ? "" : "/"}${url.replace(/\\/g, "/")}`;
      return `<img src="${norm}" alt="" loading="lazy" onerror="this.parentNode.innerHTML='<svg viewBox=\\'0 0 24 24\\' fill=\\'none\\' stroke=\\'currentColor\\' stroke-width=\\'1.6\\'><path d=\\'M11 20A7 7 0 0 1 4 13V4h9a7 7 0 0 1 7 7v9z\\'/></svg>'">`;
    }
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M11 20A7 7 0 0 1 4 13V4h9a7 7 0 0 1 7 7v9z"/><path d="M4 4l16 16"/></svg>`;
  }

  function _gzsStatusCls(s) {
    if (s === "PASS") return "et-ok";
    if (s === "CRITICAL") return "et-crit";
    if (s === "UNKNOWN") return "et-unk";
    return "et-warn";
  }

  function _gzsFmtAgo(iso) {
    if (!iso) return "—";
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return "—";
    const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
    if (sec < 60) return sec + "s ago";
    if (sec < 3600) return Math.floor(sec / 60) + "m ago";
    if (sec < 86400) return Math.floor(sec / 3600) + "h ago";
    return Math.floor(sec / 86400) + "d ago";
  }

  async function refreshZoneScansPanel(zoneKey) {
    const panel = document.getElementById("garden-zone-scans");
    const list = document.getElementById("gzs-list");
    const title = document.getElementById("gzs-title");
    if (!panel || !list || !zoneKey || typeof fetchScanHistory !== "function") return;

    // Translate Garden's short keys (a/b/c/d) into backend slugs when needed
    const slug = LOCAL_ZONE_MAP[zoneKey] || zoneKey;
    const labelMap = { zone_alpha: "Zone Alpha", zone_beta: "Zone Beta", zone_gamma: "Zone Gamma", zone_delta: "Zone Delta" };
    if (title) title.textContent = `LATEST SCANS · ${labelMap[slug] || slug.replace(/_/g, " ").toUpperCase()}`;

    panel.hidden = false;
    list.innerHTML = `<div class="gzs-empty">Loading…</div>`;

    let payload = null;
    try { payload = await fetchScanHistory({ zone: slug, limit: 5 }); } catch (_) { payload = null; }
    const scans = (payload && Array.isArray(payload.scans)) ? payload.scans : [];

    if (!scans.length) {
      list.innerHTML = `<div class="gzs-empty">No scans recorded for this zone yet.</div>`;
      return;
    }
    const cnt = scans.length;
    if (title) title.textContent = `LATEST SCANS · ${labelMap[slug] || slug} · ${cnt}`;

    const _UNK = new Set(["", "unknown", "pending", "pending analysis", "unclassified", "n/a"]);
    list.innerHTML = scans.map((s) => {
      const dRaw = (s.disease || "").trim();
      const conf = Number(s.confidence) || 0;
      const unclassified = _UNK.has(dRaw.toLowerCase()) || conf < 0.4;
      const disease = unclassified ? "Pending analysis" : dRaw;
      const confTxt = unclassified ? "—" : (conf * 100).toFixed(1) + "%";
      const statusLbl = s.status === "PASS" ? "Healthy" : (s.status === "CRITICAL" ? "Critical" : (s.status === "UNKNOWN" ? "—" : "Warn"));
      const src = s.scan_source || "—";
      return `<div class="gzs-row" data-scan-id="${s.id || ""}" role="button" tabindex="0">
        <div class="gzs-thumb">${_gzsThumb(s)}</div>
        <div class="gzs-body">
          <span class="gzs-name">${disease}</span>
          <span class="gzs-sub">${_gzsFmtAgo(s.created_at)} · ${src}</span>
        </div>
        <span class="gzs-conf">${confTxt}</span>
        <span class="entry-tag ${_gzsStatusCls(s.status)} gzs-status">${statusLbl}</span>
      </div>`;
    }).join("");

    // Bind once: row click → open scan detail
    if (!list.dataset.bound) {
      list.addEventListener("click", (e) => {
        const row = e.target.closest(".gzs-row");
        if (!row) return;
        const id = row.getAttribute("data-scan-id");
        if (window.plantAnalytics && typeof window.plantAnalytics.openScanDetail === "function") {
          window.plantAnalytics.openScanDetail(id, slug);
        }
      });
      list.dataset.bound = "1";
    }
  }

  function clearSelection() {
    selectedZoneKey = null;
    const btn = document.getElementById("garden-show-all");
    if (btn) btn.hidden = true;
    const panel = document.getElementById("garden-zone-scans");
    if (panel) panel.hidden = true;
    const map = bridge().getMap?.();
    if (map) map.flyTo([33.315, 44.366], 14, { duration: 0.6 });
    patchMarkers();
    patchZoneChips();
    patchDevicePanel();
    patchAlerts();
    patchActivity();
  }

  function patchZoneChips() {
    bridge().renderChips?.();
    const list = document.getElementById("zone-list");
    if (!list) return;
    list.querySelectorAll(".zone-chip").forEach((chip) => {
      const id = chip.dataset.zoneLocal;
      if (!id) return;
      const zones = bridge().getZones?.() || [];
      const z = zones.find((x) => x.id === id);
      if (!z) return;
      const backend = zoneBackend(z);
      const cls = backend ? statusClass(backend.status) : "off";
      const dot = chip.querySelector(".zone-chip-dot");
      if (dot) dot.className = "zone-chip-dot zcd-" + cls;
      // Phase 3 — scan-count badge (idempotent)
      const zid = localZoneId(z);
      const count = zoneScanCounts[zid] || 0;
      let badge = chip.querySelector(".zone-chip-scans");
      if (count > 0) {
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "zone-chip-scans mono";
          badge.title = "Persisted scans in this zone";
          chip.appendChild(badge);
        }
        badge.textContent = count + " scan" + (count === 1 ? "" : "s");
      } else if (badge) {
        badge.remove();
      }
      chip.classList.toggle("zone-chip-selected", selectedZoneKey === localZoneId(z));
      chip.classList.toggle("zone-chip-dimmed", selectedZoneKey && selectedZoneKey !== localZoneId(z));
      chip.classList.toggle("zch-ok", cls === "ok");
      chip.classList.toggle("zch-warn", cls === "warn");
      chip.classList.toggle("zch-crit", cls === "crit");
      chip.classList.toggle("zch-off", cls === "off");
      const blob = zoneSearchBlob(z, backend);
      const match = matchesSearch(blob, searchQuery);
      chip.classList.toggle("zone-chip-hidden", searchQuery && !match);
      const statusEl = chip.querySelector(".zone-chip-status");
      if (statusEl) {
        statusEl.textContent = z.status || mapStatus(backend?.status || "OFFLINE");
        statusEl.className = "zone-chip-status zcs-" + cls;
      }
    });
    const listEl = document.getElementById("zone-list");
    let noRes = listEl?.querySelector(".garden-search-empty");
    if (searchQuery) {
      const any = listEl && [...list.querySelectorAll(".zone-chip")].some((c) => !c.classList.contains("zone-chip-hidden"));
      if (!any) {
        if (!noRes) {
          noRes = document.createElement("div");
          noRes.className = "garden-search-empty mono";
          listEl.appendChild(noRes);
        }
        noRes.textContent = "No matching zones for \"" + searchQuery + "\"";
      } else if (noRes) noRes.remove();
    } else if (noRes) noRes.remove();
  }

  function freshnessBadge(fresh, ts) {
    const label =
      fresh === "live"
        ? "LIVE"
        : fresh === "stale"
          ? "STALE"
          : "OFFLINE";
    const ago = ts ? " — updated " + fmtAgo(ts) : "";
    return `<span class="dev-fresh dev-fresh-${fresh}">${label}${ago}</span>`;
  }

  function insightHtml(list) {
    if (!list || !list.length) return "";
    return `<div class="dev-insights">${list
      .map(
        (i) =>
          `<span class="dev-insight di-${i.tone || "pass"}">${i.label}</span>`
      )
      .join("")}</div>`;
  }

  function patchDeviceCard(card, d, reading) {
    const fresh = reading ? reading.freshness : "offline";
    const ts = reading ? reading.last_updated : null;
    const prev = devicePreview(reading);
    const badge = card.querySelector(".dev-fresh");
    if (badge) {
      const html = freshnessBadge(fresh, ts);
      const wrap = document.createElement("span");
      wrap.innerHTML = html;
      badge.replaceWith(wrap.firstChild);
    }
    const hb = card.querySelector(".dev-health-badge");
    if (hb) {
      hb.textContent = prev.health;
      hb.className = "dev-health-badge dh-" + prev.healthCls;
    }
    const preview = card.querySelector(".dev-acc-preview");
    if (preview) {
      preview.textContent = prev.insight;
      preview.className =
        "dev-acc-preview dip-" + (prev.insightTone === "off" ? "off" : prev.insightTone || "pass");
    }
    const dot = card.querySelector(".dev-dot");
    if (dot) dot.className = "dev-dot dev-dot-" + fresh;
    const set = (k, v) => {
      const el = card.querySelector(`[data-metric="${k}"]`);
      if (el && el.textContent !== String(v)) el.textContent = v;
    };
    if (reading) {
      set("temp", reading.air_temperature?.toFixed(1) ?? "—");
      set("hum", Math.round(reading.air_humidity ?? 0));
      set("lux", Math.round(reading.light_lux ?? 0));
      set("soiltemp", reading.soil_temperature?.toFixed(1) ?? "—");
      set("soil", Math.round(reading.soil_humidity ?? 0));
      set("ph", reading.soil_ph?.toFixed(1) ?? "—");
      set("ec", reading.soil_ec?.toFixed(1) ?? "—");
    }
    const ins = card.querySelector(".dev-insights");
    if (ins) ins.outerHTML = insightHtml(reading?.insights || []);
    card.querySelectorAll(".dev-spark").forEach((cv) => {
      const key = cv.getAttribute("data-series");
      drawSparkline(cv, reading?.sparklines?.[key] || []);
    });
    // Keep the subtitle in sync when a backend reading binds to this card.
    const sub = card.querySelector(".dev-acc-sub");
    if (sub) {
      const backendId = reading && reading.device_id ? reading.device_id : null;
      const subParts = [
        "Zone " + d.zoneId.toUpperCase(),
        backendId || d.device_id || null,
        d.ip || null,
      ].filter(Boolean);
      const next = subParts.join(" · ");
      if (sub.textContent !== next) sub.textContent = next;
    }
  }

  function createDeviceAccordion(d, reading) {
    const uid = d.uid;
    const open = expandedDevice === uid;
    const fresh = reading ? reading.freshness : "offline";
    const prev = devicePreview(reading);
    // Surface the live backend device_id (e.g. esp32_001) when bound so the
    // showcase audience can verify which physical sensor the card represents.
    const backendId = reading && reading.device_id ? reading.device_id : null;
    const subParts = [
      "Zone " + d.zoneId.toUpperCase(),
      backendId || d.device_id || null,
      d.ip || null,
    ].filter(Boolean);
    const article = document.createElement("article");
    article.className = "dev-accordion" + (open ? " dev-accordion-open" : "");
    article.dataset.uid = uid;
    article.innerHTML = `
      <button type="button" class="dev-acc-head">
        <span class="dev-dot dev-dot-${fresh}"></span>
        <span class="dev-acc-title">
          <span class="dev-acc-top">
            <span class="dev-name">${d.name || d.device_id || "Device"}</span>
            <span class="dev-health-badge dh-${prev.healthCls}">${prev.health}</span>
          </span>
          <span class="dev-acc-sub mono">${subParts.join(" · ")}</span>
          <span class="dev-acc-preview dip-${prev.insightTone === "off" ? "off" : prev.insightTone || "pass"}">${prev.insight}</span>
        </span>
        <span class="dev-fresh dev-fresh-${fresh}">—</span>
        <span class="dev-acc-chevron" aria-hidden="true"></span>
      </button>
      <div class="dev-acc-body">
        ${insightHtml(reading?.insights || [])}
        <div class="dev-sensor-rows">
          <div class="dev-sensors dev-sensors-env">
            <div class="dev-s"><span class="dev-s-val" data-metric="temp">—</span><span class="dev-s-lbl">Air °C</span></div>
            <div class="dev-s"><span class="dev-s-val" data-metric="hum">—</span><span class="dev-s-lbl">Humid %</span></div>
            <div class="dev-s"><span class="dev-s-val" data-metric="lux">—</span><span class="dev-s-lbl">Lux</span></div>
          </div>
          <div class="dev-sensors dev-sensors-soil">
            <div class="dev-s"><span class="dev-s-val" data-metric="soiltemp">—</span><span class="dev-s-lbl">Soil °C</span></div>
            <div class="dev-s"><span class="dev-s-val" data-metric="soil">—</span><span class="dev-s-lbl">Soil %</span></div>
            <div class="dev-s"><span class="dev-s-val" data-metric="ph">—</span><span class="dev-s-lbl">pH</span></div>
            <div class="dev-s"><span class="dev-s-val" data-metric="ec">—</span><span class="dev-s-lbl">EC</span></div>
          </div>
        </div>
        <div class="dev-spark-row">
          <span class="dev-spark-lbl">Temp</span><canvas class="dev-spark" data-series="air_temperature" width="72" height="22"></canvas>
          <span class="dev-spark-lbl">Hum</span><canvas class="dev-spark" data-series="air_humidity" width="72" height="22"></canvas>
          <span class="dev-spark-lbl">Soil</span><canvas class="dev-spark" data-series="soil_humidity" width="72" height="22"></canvas>
        </div>
      </div>`;
    const head = article.querySelector(".dev-acc-head");
    head.addEventListener("click", () => {
      expandedDevice = expandedDevice === uid ? null : uid;
      article.classList.toggle("dev-accordion-open", expandedDevice === uid);
    });
    patchDeviceCard(article, d, reading);
    return article;
  }

  function getVisibleDevices() {
    const all = bridge().getAllDevices?.() || [];
    let list = all;
    if (selectedZoneKey) {
      list = list.filter((d) => {
        const zones = bridge().getZones?.() || [];
        const z = zones.find((x) => x.id === d.zoneId);
        return z && localZoneId(z) === selectedZoneKey;
      });
    }
    if (searchQuery) {
      const q = searchQuery;
      list = list.filter((d) => {
        const zones = bridge().getZones?.() || [];
        const z = zones.find((x) => x.id === d.zoneId);
        const backend = z ? zoneBackend(z) : null;
        const blob = [
          d.name,
          d.ip,
          d.zoneId,
          d.device_id,
          z ? zoneSearchBlob(z, backend) : "",
        ]
          .join(" ")
          .toLowerCase();
        return matchesSearch(blob, q);
      });
    }
    return list;
  }

  function patchDevicePanel() {
    const panel = document.getElementById("device-panel");
    const counter = document.getElementById("device-counter");
    if (!panel) return;
    const visible = getVisibleDevices();
    if (counter) {
      counter.textContent = selectedZoneKey
        ? `${visible.length} in zone`
        : `${visible.length} devices`;
    }

    if (!visible.length) {
      const msg = searchQuery
        ? "No matching devices"
        : selectedZoneKey
          ? "No devices in this zone"
          : "Awaiting live sensor stream";
      const hint = searchQuery
        ? "Try zone name, ESP32 ID, or status keyword."
        : selectedZoneKey
          ? "Add devices in zone settings or show all zones."
          : "Connect ESP32 devices or post to /sensor to populate readings.";
      const emptyHtml = gardenEmptyHtml("📡", msg, hint, "dev-no-devices");
      const cur = panel.querySelector(".dev-no-devices");
      if (!cur) panel.innerHTML = emptyHtml;
      else if (cur.querySelector(".garden-empty-title")?.textContent !== msg) cur.outerHTML = emptyHtml;
      return;
    }

    const empty = panel.querySelector(".dev-no-devices");
    if (empty) empty.remove();

    // First time garden.js owns the panel, wipe any legacy app.js demo
    // cards (they use IDs like dv-a_0-temp; we use data-uid="<zone>_<idx>").
    if (!panel.dataset.gardenOwned) {
      panel.dataset.gardenOwned = "1";
      panel.innerHTML = "";
      deviceCardEls.clear();
    }

    const existing = new Set();
    visible.forEach((d) => {
      existing.add(d.uid);
      let card = deviceCardEls.get(d.uid) || panel.querySelector(`[data-uid="${d.uid}"]`);
      const reading = deviceReading(
        (bridge().getZones?.() || []).find((z) => z.id === d.zoneId),
        { device_id: d.device_id || d.name, name: d.name },
        parseInt(d.uid.split("_")[1], 10) || 0
      );
      if (!card) {
        card = createDeviceAccordion(d, reading);
        panel.appendChild(card);
        deviceCardEls.set(d.uid, card);
      } else {
        patchDeviceCard(card, d, reading);
      }
    });

    deviceCardEls.forEach((card, uid) => {
      if (!existing.has(uid)) {
        card.remove();
        deviceCardEls.delete(uid);
      }
    });
  }

  function patchAlerts() {
    const list = document.getElementById("garden-alert-list");
    if (!list || !dashboard) return;
    let alerts = dashboard.alerts || [];
    if (selectedZoneKey) {
      alerts = alerts.filter((a) => a.zone_id === selectedZoneKey);
    }
    if (searchQuery) {
      const q = searchQuery;
      alerts = alerts.filter((a) => {
        const blob = [a.message, a.zone_id, a.event_type].filter(Boolean).join(" ").toLowerCase();
        return matchesSearch(blob, q);
      });
    }
    alerts = alerts.slice(0, 15);

    const key = stableStringify(alerts);
    if (key === lastAlertKey) return;
    lastAlertKey = key;

    const existingIds = new Set();
    alerts.forEach((a, i) => {
      existingIds.add(a.id);
      let row = alertEls.get(a.id);
      const cat = alertCategory(a);
      const ico = { crit: "✕", warn: "!", info: "✓", sys: "◈" }[cat] || "✓";
      const html = `<div class="alert-item alert-${cat}${i === 0 ? " alert-item-new" : ""}" data-alert-id="${a.id}">
        <span class="alert-ico">${ico}</span>
        <div class="alert-body"><span class="alert-msg">${a.message}</span><span class="alert-time mono">${fmtAgo(a.timestamp)}</span></div>
      </div>`;
      if (!row) {
        const wrap = document.createElement("div");
        wrap.innerHTML = html;
        row = wrap.firstElementChild;
        if (row) {
          list.insertBefore(row, list.firstChild);
          alertEls.set(a.id, row);
          if ((cat === "crit" || cat === "warn") && a.zone_id) flashZoneMarker(a.zone_id);
        }
      } else if (row.outerHTML !== html) {
        const wasNew = row.classList.contains("alert-item-new");
        row.outerHTML = html;
        row = list.querySelector(`[data-alert-id="${a.id}"]`);
        alertEls.set(a.id, row);
        if (wasNew) row?.classList.add("alert-item-new");
      }
    });

    alertEls.forEach((row, id) => {
      if (!existingIds.has(id)) {
        row.remove();
        alertEls.delete(id);
      }
    });

    if (!alerts.length) {
      list.innerHTML = gardenEmptyHtml("✓", searchQuery ? "No matching alerts" : "All clear — no active alerts", searchQuery ? "Adjust search or clear the filter." : "Monitoring continues in the background.", "garden-alert-empty");
    } else {
      const empty = list.querySelector(".garden-alert-empty");
      if (empty) empty.remove();
    }
  }

  function patchActivity() {
    const list = document.getElementById("garden-activity-list");
    if (!list || !dashboard) return;
    let items = dashboard.activity || [];
    if (selectedZoneKey) {
      items = items.filter((a) => a.zone_id === selectedZoneKey);
    }
    if (searchQuery) {
      items = items.filter((a) =>
        matchesSearch((a.message || "").toLowerCase() + " " + (a.zone_id || ""), searchQuery)
      );
    }
    const html = items
      .slice(0, 12)
      .map(
        (a) =>
          `<div class="garden-act-item garden-act-${a.severity}"><span class="garden-act-time mono">${fmtTime(a.timestamp)}</span><span class="garden-act-msg">${a.message}</span></div>`
      )
      .join("");
    if (list.innerHTML !== html) {
      if (html) list.innerHTML = html;
      else
        list.innerHTML = gardenEmptyHtml("◎", "Awaiting zone activity", "Scans and sensor events will appear here.", "garden-act-empty");
    }
  }

  function applyDashboard(data) {
    dashboard = data;
    lastDataRefresh = Date.now();
    const zones = bridge().getZones?.() || [];
    zones.forEach((z) => {
      const b = zoneBackend(z);
      if (b) z.status = mapStatus(b.status);
    });
    patchSummary();
    patchMarkers();
    patchZoneChips();
    patchDevicePanel();
    patchAlerts();
    patchActivity();
    const key = stableStringify(data);
    lastSnapshot = key + "|" + stableStringify(data.alerts);
  }

  async function refreshGarden(force) {
    if (typeof fetchGardenDashboard !== "function") return;

    // Prime the unified sensor context so patchSummary() / patchDevicePanel()
    // see fresh freshness data. Cached/coalesced inside api.js.
    if (window.plantSensor && typeof window.plantSensor.get === "function") {
      try { await window.plantSensor.get(force); } catch (_) {}
    }

    if (typeof fetchAnalyticsHistory === "function") {
      try {
        const hist = await fetchAnalyticsHistory(50);
        indexScansFromHistory(hist || []);
      } catch (_) {}
    }

    // Phase 3 — refresh per-zone scan counts (badge on chips + tooltip).
    // Coalesce to ~15s unless force is true, so the regular Garden poll
    // doesn't beat the DB on every tick.
    const nowMs = Date.now();
    if (typeof fetchZoneScanCounts === "function" && (force || nowMs - zoneScanCountsAt > 15000)) {
      try {
        const counts = await fetchZoneScanCounts();
        if (counts && counts.counts) {
          // Reset and repopulate
          Object.keys(zoneScanCounts).forEach((k) => delete zoneScanCounts[k]);
          Object.assign(zoneScanCounts, counts.counts);
          zoneScanCountsAt = nowMs;
        }
      } catch (_) {}
    }
    const res = await fetchGardenDashboard();
    if (res.ok && res.data) {
      applyDashboard(res.data);
      return;
    }
    if (force) {
      const tag = document.getElementById("garden-live-tag");
      if (tag) {
        tag.textContent = "● Offline";
        tag.style.color = "var(--coral)";
      }
    }
  }

  function wireSearch() {
    /**
     * The map search bar (#map-search) is a GEOGRAPHIC location search wired in
     * app.js → initMapSearch() (Nominatim geocoding via /api/geocode).
     * Zone / device / alert filtering would be a separate UI control if ever
     * added. We intentionally leave searchQuery empty here so all garden
     * markers, chips, devices, and alerts remain visible regardless of what
     * the user types into the map search bar.
     */
    searchQuery = "";
  }

  function onNavigate(targetId) {
    if (targetId === "page-garden") {
      if (window._stopSensorSimulation) window._stopSensorSimulation();
      setTimeout(() => {
        refreshGarden(true);
        if (!pollTimer) pollTimer = setInterval(() => refreshGarden(false), POLL_MS);
        const map = bridge().getMap?.();
        if (map) map.invalidateSize();
      }, 120);
    }
  }

  function onZonesChanged() {
    patchMarkers();
    patchZoneChips();
    patchDevicePanel();
  }

  window.plantGarden = {
    refresh: refreshGarden,
    onNavigate,
    onZonesChanged,
    selectZone,
    clearSelection,
    hasSelection: () => !!selectedZoneKey,
    /**
     * Returns the currently selected zone slug ("zone_alpha" form), or null
     * if no zone is selected on the Garden map. Used by the scan pipeline
     * to attribute scans to the user's active zone selection.
     */
    getSelectedZoneSlug: () => selectedZoneKey || null,
    pulseZone: (zoneKey) => flashZoneMarker(zoneKey),
  };

  wireSearch();
  document.getElementById("garden-show-all")?.addEventListener("click", clearSelection);
  document.getElementById("gzs-close")?.addEventListener("click", () => {
    const panel = document.getElementById("garden-zone-scans");
    if (panel) panel.hidden = true;
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => refreshGarden(false));
  }
})();
