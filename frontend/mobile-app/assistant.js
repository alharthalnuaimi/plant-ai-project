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
      const [health, summary, events, sensorRes] = await Promise.all([
        typeof fetchPlantHealth === "function" ? fetchPlantHealth() : null,
        typeof fetchAnalyticsSummary === "function" ? fetchAnalyticsSummary() : null,
        typeof fetchAnalyticsEvents === "function" ? fetchAnalyticsEvents(12) : null,
        typeof fetchSensorLatest === "function"
          ? fetchSensorLatest().catch(() => null)
          : null,
      ]);
      if (health) ctx.lastHealth = health;
      if (summary) ctx.summary = summary;
      if (events) ctx.events = events;
      if (sensorRes && sensorRes.reading) ctx.lastSensor = sensorRes.reading;
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
      lines.push(
        `Sensor: air ${s.air_temperature}°C, humidity ${s.air_humidity}%, soil moisture ${s.soil_humidity}%.`
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

  function buildZoneReply(lower) {
    const zid = window.PLANT_ZONE_ID || "zone_alpha";
    let target = zid;
    if (lower.includes("beta")) target = "zone_beta";
    else if (lower.includes("gamma")) target = "zone_gamma";
    else if (lower.includes("delta")) target = "zone_delta";
    else if (lower.includes("alpha")) target = "zone_alpha";

    const ev = ctx.events.find((e) => e.zone_id === target);
    const scan =
      ctx.lastScan && (ctx.lastScan.zone_id || zid) === target ? ctx.lastScan : null;
    let msg = `${zoneLabel(target)} status:\n`;
    if (scan) {
      msg += `Latest scan: ${scan.disease} (${fmtConf(scan.confidence)}).\n`;
    } else if (ev) {
      msg += `Recent activity: ${ev.message}.\n`;
    } else {
      msg += "No recent scan for this zone in the current session.\n";
    }
    if (ctx.lastHealth) {
      msg += `Health score ~${ctx.lastHealth.plant_health}% for current operator context.`;
    }
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
    if (!ctx.lastScan) {
      return "No scan in this session. Open the scanner on Home or tap the camera icon here to diagnose a leaf.";
    }
    const s = ctx.lastScan;
  const h = s.health;
    let msg = `Latest scan: ${s.disease} — confidence ${fmtConf(s.confidence)} (${s.class_name || s.disease_type || "classified"}).`;
    if (h) {
      msg += ` Health ${h.plant_health}%, risk ${h.disease_risk}. ${h.recommendation}`;
    }
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
})();
