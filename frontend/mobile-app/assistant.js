/**
 * Rule-based contextual AI assistant (no external API).
 */
(function () {
  const ctx = {
    lastScan: null,
    lastHealth: null,
    lastSensor: null,
    summary: null,
    events: [],
    updatedAt: 0,
    // Phase 3 correction — cached per-zone scan count + latest persisted
    // scan, so "How is Zone Alpha?" can answer synchronously even after a
    // page reload, without an in-session scan.
    zoneCounts: {},
    zoneLatest: {},   // zone_slug -> latest ScanListItem from /scans/history
  };

  const ZONE_LABELS = {
    zone_alpha: "Zone Alpha",
    zone_beta: "Zone Beta",
    zone_gamma: "Zone Gamma",
    zone_delta: "Zone Delta",
  };

  function zoneLabel(zid) {
    return ZONE_LABELS[zid] || (zid || "zone").replace(/_/g, " ");
  }

  function fmtPct(n) {
    if (n == null || Number.isNaN(n)) return "—";
    return Math.round(n) + "%";
  }

  function fmtConf(c) {
    if (c == null) return "—";
    return (c * 100).toFixed(1) + "%";
  }

  async function refreshContext() {
    const base = window.PLANT_API_BASE;
    if (!base) return;
    try {
      const [health, summary, events, history, sensorCtx, zoneCounts, richHistory] = await Promise.all([
        typeof fetchPlantHealth === "function" ? fetchPlantHealth() : null,
        typeof fetchAnalyticsSummary === "function" ? fetchAnalyticsSummary() : null,
        typeof fetchAnalyticsEvents === "function" ? fetchAnalyticsEvents(12) : null,
        typeof fetchAnalyticsHistory === "function" ? fetchAnalyticsHistory(1) : null,
        window.plantSensor && typeof window.plantSensor.get === "function"
          ? window.plantSensor.get()
          : null,
        typeof fetchZoneScanCounts === "function" ? fetchZoneScanCounts() : null,
        typeof fetchScanHistory === "function" ? fetchScanHistory({ limit: 30 }) : null,
      ]);

      // Cache zone-scan counts (Phase 3 correction).
      if (zoneCounts && zoneCounts.counts) ctx.zoneCounts = zoneCounts.counts;

      // Cache latest persisted scan per zone so "How is Zone X?" works.
      if (richHistory && Array.isArray(richHistory.scans)) {
        const seen = {};
        for (const s of richHistory.scans) {
          if (s && s.zone_id && !seen[s.zone_id]) seen[s.zone_id] = s;
        }
        ctx.zoneLatest = seen;
      }
      if (health) ctx.lastHealth = health;
      if (summary) ctx.summary = summary;
      if (events) ctx.events = events;
      // Hydrate lastScan from the persisted history so the assistant can
      // answer "what was the last scan?" even after a page reload.
      if (!ctx.lastScan && Array.isArray(history) && history.length) {
        const h = history[0];
        ctx.lastScan = {
          disease: h.disease,
          confidence: h.confidence,
          zone_id: h.zone_id,
          status: h.status,
          scan_id: h.scan_id,
          timestamp: h.timestamp,
          health: ctx.lastHealth || null,
        };
      }
      if (sensorCtx && sensorCtx.reading) {
        ctx.lastSensor = sensorCtx.reading;
        ctx.sensorMode = sensorCtx.mode;
        ctx.sensorFreshness = sensorCtx.freshness;
        ctx.sensorAgeSec = sensorCtx.age_seconds;
      } else {
        ctx.lastSensor = null;
        ctx.sensorMode = "simulation";
        ctx.sensorFreshness = "none";
        ctx.sensorAgeSec = null;
      }
      ctx.updatedAt = Date.now();
    } catch (_) {
      /* offline */
    }
  }

  function setLastScan(result) {
    ctx.lastScan = result;
    if (result && result.health) ctx.lastHealth = result.health;
    ctx.updatedAt = Date.now();
  }

  function matches(lower, words) {
    return words.some((w) => lower.includes(w));
  }

  function buildPlantStatusReply() {
    const zid = window.PLANT_ZONE_ID || "zone_alpha";
    const scan = ctx.lastScan;
    const health = ctx.lastHealth || (scan && scan.health);
    const lines = [];

    if (scan) {
      lines.push(
        `${zoneLabel(scan.zone_id || zid)} latest scan: ${scan.disease || "unknown"} at ${fmtConf(scan.confidence)} confidence.`
      );
    } else if (ctx.summary && ctx.summary.total_scans > 0) {
      lines.push(
        `No scan in this session yet. Analytics shows ${ctx.summary.total_scans} total scan(s), avg confidence ${fmtPct((ctx.summary.avg_confidence || 0) * 100)}.`
      );
    } else {
      lines.push("No scans recorded yet. Use Home or the chat camera to run a plant scan.");
    }

    if (ctx.lastSensor) {
      const s = ctx.lastSensor;
      const tag = ctx.sensorFreshness === "live"
        ? "[LIVE]"
        : ctx.sensorFreshness === "stale"
          ? "[STALE]"
          : "[OFFLINE]";
      lines.push(
        `Sensor ${tag} air ${s.air_temperature}°C, humidity ${s.air_humidity}%, soil moisture ${s.soil_humidity}%.`
      );
    } else {
      lines.push("Sensor feed: awaiting live stream (demo values may apply).");
    }

    if (health) {
      lines.push(
        `Plant health estimated at ${health.plant_health}% — disease risk ${health.disease_risk}, environment stress ${health.environment_stress}, survival chance ${health.survival_chance}%.`
      );
      if (health.recommendation) lines.push("Recommendation: " + health.recommendation);
    }

    return lines.join("\n");
  }

  function _classifiedDisease(s) {
    const d = (s && s.disease) ? String(s.disease).trim() : "";
    if (!d) return "Pending analysis";
    if (/^(unknown|pending|unclassified|n\/a)$/i.test(d)) return "Pending analysis";
    return d;
  }

  function _classifiedConf(s) {
    if (!s) return "—";
    const d = (s.disease || "").trim();
    if (!d || /^(unknown|pending|unclassified|n\/a)$/i.test(d)) return "—";
    return fmtConf(s.confidence);
  }

  function buildZoneReply(lower) {
    const zid = window.PLANT_ZONE_ID || "zone_alpha";
    let target = zid;
    if (lower.includes("beta")) target = "zone_beta";
    else if (lower.includes("gamma")) target = "zone_gamma";
    else if (lower.includes("delta")) target = "zone_delta";
    else if (lower.includes("alpha")) target = "zone_alpha";

    const ev = ctx.events.find((e) => e.zone_id === target);
    // Prefer in-session scan, then last persisted scan for the zone.
    const sessionScan =
      ctx.lastScan && (ctx.lastScan.zone_id || zid) === target ? ctx.lastScan : null;
    const scan = sessionScan || ctx.zoneLatest[target] || null;
    const count = ctx.zoneCounts[target] || 0;

    let msg = `${zoneLabel(target)} status:\n`;

    // Live sensor snapshot for this zone (if available via the unified context)
    const sensorCtx = window.plantSensor && typeof window.plantSensor.last === "function"
      ? window.plantSensor.last() : null;
    if (sensorCtx && sensorCtx.reading && sensorCtx.reading.zone_id === target) {
      const r = sensorCtx.reading;
      const freshness = sensorCtx.freshness || sensorCtx.mode || "—";
      msg += `Sensor (${freshness}): ${r.air_temperature?.toFixed?.(1) ?? r.air_temperature}°C · ${Math.round(r.air_humidity)}% RH · pH ${r.soil_ph}.\n`;
    } else {
      msg += `Sensor: no live reading for this zone yet.\n`;
    }

    if (scan) {
      const meta = scan.metadata || {};
      const plant = meta.plant_id || scan.plant_id;
      const h = scan.health;
      const health = h ? h.plant_health : scan.health_score;
      const risk   = h ? h.disease_risk : scan.risk_level;
      const rec    = (h && h.recommendation) || scan.recommendation || (meta && meta.recommendation);
      msg += `Latest scan: ${_classifiedDisease(scan)} (${_classifiedConf(scan)}).`;
      if (plant) msg += `\nPlant: ${plant}.`;
      if (health != null) msg += `\nHealth ${health}%${risk ? " · risk " + risk : ""}.`;
      if (rec) msg += `\n${rec}`;
      msg += "\n";
    } else if (ev) {
      msg += `Recent activity: ${ev.message}.\n`;
    } else {
      msg += "No recent scan for this zone yet.\n";
    }

    msg += `Persisted scans in this zone: ${count}.`;
    return msg;
  }

  function buildWhatHappenedReply() {
    if (!ctx.events.length) {
      return "No recent events yet. Scans, sensor updates, and alerts will appear in the activity feed.";
    }
    return (
      "Recent activity:\n" +
      ctx.events
        .slice(0, 5)
        .map((e) => "• " + (e.message || e.event_type))
        .join("\n")
    );
  }

  function buildLatestScanReply() {
    // Fall back to the latest persisted scan from any zone if the session
    // is fresh (page reload, no in-session scan yet).
    let s = ctx.lastScan;
    if (!s) {
      const persistedZones = Object.values(ctx.zoneLatest || {});
      if (persistedZones.length) {
        persistedZones.sort((a, b) => (Date.parse(b.created_at || 0) || 0) - (Date.parse(a.created_at || 0) || 0));
        s = persistedZones[0];
      }
    }
    if (!s) {
      return "No scan in this session. Open the scanner on Home or tap the camera icon here to diagnose a leaf.";
    }
    const h = s.health;
    const zoneName = zoneLabel(s.zone_id || (window.PLANT_ZONE_ID || "zone_alpha"));
    const meta = s.metadata || {};
    const deviceId = meta.device_id || s.device_id || (window.PLANT_DEVICE_ID || "esp32_001");
    const plantId = meta.plant_id || s.plant_id || "";
    const source = meta.scan_source || s.scan_source || "";
    const disease = _classifiedDisease(s);
    const confTxt = _classifiedConf(s);
    const klass = s.class_name || s.disease_type || meta.class_name || "classified";
    const healthScore = (h && h.plant_health != null) ? h.plant_health : s.health_score;
    const risk        = (h && h.disease_risk)         ? h.disease_risk : s.risk_level;
    const survival    = (h && h.survival_chance != null) ? h.survival_chance : s.survival_score;
    const rec         = (h && h.recommendation) || s.recommendation || meta.recommendation || "";

    let msg = `Latest scan in ${zoneName}: ${disease} — confidence ${confTxt} (${klass}).`;
    if (plantId) msg += `\nPlant: ${plantId}.`;
    msg += `\nDevice: ${deviceId}${source ? " · source " + source : ""}.`;
    if (healthScore != null) {
      msg += `\nHealth ${healthScore}%${risk ? " · risk " + risk : ""}${survival != null ? " · survival " + survival + "%" : ""}.`;
    }
    if (rec) msg += `\n${rec}`;
    return msg;
  }

  function buildActionReply() {
    const h = ctx.lastHealth;
    if (h && h.recommendation) return h.recommendation;
    if (ctx.lastScan && ctx.lastScan.health) return ctx.lastScan.health.recommendation;
    return "Run a scan first, then I can suggest actions based on disease class and sensor stress.";
  }

  function getContextualReply(msg) {
    const lower = (msg || "").toLowerCase().trim();
    if (!lower) return "Ask about plant health, your latest scan, zone status, or what to do next.";

    if (
      matches(lower, [
        "how is my plant",
        "how's my plant",
        "plant health",
        "how healthy",
        "status of my plant",
      ])
    ) {
      return buildPlantStatusReply();
    }
    if (matches(lower, ["zone alpha", "zone beta", "zone gamma", "zone delta", "how is zone"])) {
      return buildZoneReply(lower);
    }
    if (matches(lower, ["what happened", "recent activity", "what's new", "updates"])) {
      return buildWhatHappenedReply();
    }
    if (matches(lower, ["latest scan", "last scan", "recent scan", "my scan"])) {
      return buildLatestScanReply();
    }
    if (
      matches(lower, [
        "what should i do",
        "what do i do",
        "recommend",
        "advice",
        "help me",
        "treatment",
      ])
    ) {
      return buildActionReply();
    }
    if (matches(lower, ["health score", "survival", "disease risk"])) {
      const h = ctx.lastHealth;
      if (!h) return "Health score not available yet — run a scan or open Profile for live scoring.";
      return `Plant health ${h.plant_health}%. Disease risk: ${h.disease_risk}. Environment stress: ${h.environment_stress}. Survival chance: ${h.survival_chance}%. ${h.recommendation}`;
    }

    return null;
  }

  window.plantAssistant = {
    refreshContext,
    setLastScan,
    getContextualReply,
    getContext: () => ({ ...ctx }),
  };

  refreshContext();
  setInterval(refreshContext, 12000);
  // Re-cache zone counts + zone latest immediately after each scan so the
  // assistant's first reply post-scan already reflects the new total.
  window.addEventListener("plantvision:scan-complete", () => {
    refreshContext().catch(() => {});
  });
})();
