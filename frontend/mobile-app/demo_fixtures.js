/**
 * PlantVision — Demo Mode fixtures (Phase 4 / A3).
 *
 * Why this file exists
 * --------------------
 * Demo mode is a frontend-only escape hatch so the dashboard still
 * looks like a working product when:
 *   * the ESP32 sensor node is unplugged / out of WiFi range,
 *   * the FastAPI backend is asleep (Railway free tier cold start),
 *   * Supabase is unreachable (network down, key rotated, …),
 *   * the user is offline entirely (presentation room, plane, etc.).
 *
 * When `window.plantDemo.isOn()` is true, `api.js` short-circuits its
 * outbound fetches and returns the canned objects below INSTEAD of
 * hitting the real backend. The shapes here intentionally match the
 * real /sensor, /scans, /report, /health/plant, etc. response shapes so
 * downstream rendering code is unchanged.
 *
 * All values describe a moderately stressed cucumber plant in Zone
 * Alpha so the dashboard tells a coherent story:
 *   * temp 24°C, humidity 62%, soil moisture 55%, lux 28k, pH 6.4, EC 2.0
 *   * latest scan: Powdery Mildew, conf=0.78, health=72
 *   * 5 historical scans across two zones
 *
 * Never persist these to the backend — they are presentation-only.
 */

(function () {
  "use strict";

  const STORAGE_KEY = "PLANT_DEMO_MODE";
  const SCENARIO_KEY = "PLANT_DEMO_SCENARIO";   // "healthy" | "warning"
  const SESSION_USER = "demo_user";
  const SESSION_ZONE = "zone_alpha";
  const SESSION_DEVICE = "esp32_001";

  // ------------------------------------------------------------------
  // Toggle state
  // ------------------------------------------------------------------
  function isOn() {
    try {
      return localStorage.getItem(STORAGE_KEY) === "1";
    } catch (_) {
      return false;
    }
  }

  function setOn(on) {
    try {
      if (on) localStorage.setItem(STORAGE_KEY, "1");
      else localStorage.setItem(STORAGE_KEY, "0");
    } catch (_) {
      /* localStorage blocked → demo mode silently no-ops */
    }
    _broadcast(on);
    return Boolean(on);
  }

  function toggle() {
    return setOn(!isOn());
  }

  function _broadcast(on) {
    try {
      window.dispatchEvent(
        new CustomEvent("plantvision:demo-mode-changed", { detail: { on: Boolean(on) } })
      );
    } catch (_) { /* IE shim not needed */ }
  }

  // ------------------------------------------------------------------
  // Phase Final — scenario toggle. Defaults to the more demo-impressive
  // "warning" scenario (early powdery mildew) so the professor sees the
  // dashboard react with warnings + care card. Switch to "healthy" from
  // Settings → Demo Mode → Scenario.
  // ------------------------------------------------------------------
  function scenario() {
    try {
      const v = (localStorage.getItem(SCENARIO_KEY) || "warning").toLowerCase();
      return v === "healthy" ? "healthy" : "warning";
    } catch (_) { return "warning"; }
  }
  function setScenario(name) {
    const v = String(name || "").toLowerCase() === "healthy" ? "healthy" : "warning";
    try { localStorage.setItem(SCENARIO_KEY, v); } catch (_) { /* noop */ }
    try {
      window.dispatchEvent(new CustomEvent("plantvision:demo-scenario-changed", { detail: { scenario: v } }));
    } catch (_) {}
    return v;
  }
  function isHealthy() { return scenario() === "healthy"; }

  // ------------------------------------------------------------------
  // Stylised SVG data-URI thumbnails. Self-contained so demo scans
  // never reference broken URLs even when no backend is up — and so we
  // don't need to ship binary leaf JPGs that would bloat the repo.
  // ------------------------------------------------------------------
  function _leafThumbDataUri(variant) {
    const palette = variant === "healthy"
      ? { bg1: "#1f3a2a", bg2: "#274632", leaf: "#8ca88c", vein: "#cfe0c8" }
      : { bg1: "#3a2d1f", bg2: "#46382a", leaf: "#c0a06a", vein: "#e6d4a8" };
    const svg =
      `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 96 96'>` +
      `<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>` +
      `<stop offset='0' stop-color='${palette.bg1}'/>` +
      `<stop offset='1' stop-color='${palette.bg2}'/>` +
      `</linearGradient></defs>` +
      `<rect width='96' height='96' fill='url(#g)'/>` +
      `<path d='M70 18 C 38 22 22 38 18 70 L 22 74 C 26 50 50 26 74 22 Z' fill='${palette.leaf}' opacity='0.92'/>` +
      `<path d='M70 18 L 22 74' stroke='${palette.vein}' stroke-width='1.4' opacity='0.55'/>` +
      `<path d='M58 22 L 30 50' stroke='${palette.vein}' stroke-width='1' opacity='0.4'/>` +
      `<path d='M74 30 L 46 58' stroke='${palette.vein}' stroke-width='1' opacity='0.4'/>` +
      `</svg>`;
    return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
  }

  // ------------------------------------------------------------------
  // Time helpers — keep fixtures looking "live" without code edits.
  // ------------------------------------------------------------------
  function nowIso() { return new Date().toISOString(); }
  function nowSec() { return Math.floor(Date.now() / 1000); }
  function isoMinutesAgo(min) {
    return new Date(Date.now() - min * 60 * 1000).toISOString();
  }
  function secMinutesAgo(min) {
    return nowSec() - min * 60;
  }

  // ------------------------------------------------------------------
  // Canned data
  // ------------------------------------------------------------------
  function sensorReading() {
    const healthy = isHealthy();
    return {
      user_id: SESSION_USER,
      zone_id: SESSION_ZONE,
      device_id: SESSION_DEVICE,
      air_temperature: healthy ? 23.4 : 24.0,
      air_humidity: healthy ? 55.0 : 62.0,
      light_lux: healthy ? 30000.0 : 28000.0,
      soil_temperature: healthy ? 22.0 : 22.0,
      soil_humidity: healthy ? 62.0 : 55.0,
      soil_ph: 6.4,
      soil_ec: healthy ? 2.1 : 2.0,
      timestamp: nowIso(),
      status: {
        air_temperature_status: "normal",
        air_humidity_status: "normal",
        light_status: "normal",
        soil_temperature_status: "normal",
        soil_humidity_status: "normal",
        ph_status: "normal",
        ec_status: "normal",
        overall_environment_status: "healthy",
      },
      metadata: { source: "demo_fixture", firmware: "esp32-demo-1.0.0", scenario: scenario() },
    };
  }

  function sensorLatestEnvelope() {
    return {
      source: "live",
      freshness: "live",
      age_seconds: 4.2,
      reading: sensorReading(),
    };
  }

  function plantHealth() {
    if (isHealthy()) {
      return {
        plant_health: 92,
        disease_risk: "low",
        stress_level: "low",
        environment_stress: "minimal",
        survival_chance: 96,
        class_name: "healthy",
        disease_type: "none",
        recommendation:
          "Cucumber is thriving. Keep watering schedule consistent and rotate the " +
          "plant 90° once a week so all sides receive even light.",
        accepted: true,
        source: "demo",
      };
    }
    return {
      plant_health: 72,
      disease_risk: "medium",
      stress_level: "low",
      environment_stress: "mild",
      survival_chance: 68,
      class_name: "powdery_mildew",
      disease_type: "fungal",
      recommendation:
        "Mild powdery mildew detected. Increase airflow, reduce overhead watering, " +
        "and consider a sulphur or potassium bicarbonate spray within 24–48h.",
      accepted: true,
      source: "demo",
    };
  }

  function scanHistory(limit) {
    const max = Math.max(1, Math.min(limit || 5, 7));
    const healthy = isHealthy();
    const thumbWarn = _leafThumbDataUri("warning");
    const thumbOk = _leafThumbDataUri("healthy");
    // Latest scan flips with scenario so the dashboard's hero ring,
    // care card, and warnings strip all tell a consistent story.
    const latest = healthy
      ? {
          id: "demo-scan-001",
          scan_id: "demo-scan-001",
          plant_id: "cucumber_001",
          zone_id: SESSION_ZONE,
          device_id: SESSION_DEVICE,
          disease: "Healthy",
          confidence: 0.96,
          status: "PASS",
          health_score: 92,
          risk_level: "low",
          accepted: true,
          timestamp: secMinutesAgo(3),
          created_at: isoMinutesAgo(3),
          image_url: thumbOk,
          metadata: { source: "demo_fixture", model: "demo-stub", image_url: thumbOk },
        }
      : {
          id: "demo-scan-001",
          scan_id: "demo-scan-001",
          plant_id: "cucumber_001",
          zone_id: SESSION_ZONE,
          device_id: SESSION_DEVICE,
          disease: "Powdery Mildew",
          confidence: 0.78,
          status: "WARN",
          health_score: 72,
          risk_level: "medium",
          accepted: true,
          timestamp: secMinutesAgo(3),
          created_at: isoMinutesAgo(3),
          image_url: thumbWarn,
          metadata: { source: "demo_fixture", model: "demo-stub", image_url: thumbWarn },
        };
    const base = [
      latest,
      {
        id: "demo-scan-002",
        scan_id: "demo-scan-002",
        plant_id: "cucumber_001",
        zone_id: SESSION_ZONE,
        device_id: SESSION_DEVICE,
        disease: "Healthy",
        confidence: 0.94,
        status: "PASS",
        health_score: 91,
        risk_level: "low",
        accepted: true,
        timestamp: secMinutesAgo(42),
        created_at: isoMinutesAgo(42),
        image_url: thumbOk,
        metadata: { source: "demo_fixture", model: "demo-stub", image_url: thumbOk },
      },
      {
        id: "demo-scan-003",
        scan_id: "demo-scan-003",
        plant_id: "tomato_002",
        zone_id: "zone_beta",
        device_id: "esp32_002",
        disease: "Leaf Spot",
        confidence: 0.66,
        status: "WARN",
        health_score: 64,
        risk_level: "medium",
        accepted: true,
        timestamp: secMinutesAgo(180),
        created_at: isoMinutesAgo(180),
        image_url: thumbWarn,
        metadata: { source: "demo_fixture", model: "demo-stub", image_url: thumbWarn },
      },
      {
        id: "demo-scan-004",
        scan_id: "demo-scan-004",
        plant_id: "cucumber_001",
        zone_id: SESSION_ZONE,
        device_id: SESSION_DEVICE,
        disease: "Healthy",
        confidence: 0.88,
        status: "PASS",
        health_score: 88,
        risk_level: "low",
        accepted: true,
        timestamp: secMinutesAgo(420),
        created_at: isoMinutesAgo(420),
        image_url: thumbOk,
        metadata: { source: "demo_fixture", model: "demo-stub", image_url: thumbOk },
      },
      {
        id: "demo-scan-005",
        scan_id: "demo-scan-005",
        plant_id: "pepper_bell_003",
        zone_id: "zone_gamma",
        device_id: "esp32_003",
        disease: "Aphid Stress",
        confidence: 0.71,
        status: "CRITICAL",
        health_score: 48,
        risk_level: "high",
        accepted: true,
        timestamp: secMinutesAgo(1440),
        created_at: isoMinutesAgo(1440),
        image_url: thumbWarn,
        metadata: { source: "demo_fixture", model: "demo-stub", image_url: thumbWarn },
      },
      // Two extra older scans so the Phase Final trend chart has 7 points
      // to draw a smooth curve when Demo Mode is on.
      {
        id: "demo-scan-006",
        scan_id: "demo-scan-006",
        plant_id: "cucumber_001",
        zone_id: SESSION_ZONE,
        device_id: SESSION_DEVICE,
        disease: "Healthy",
        confidence: 0.9,
        status: "PASS",
        health_score: 85,
        risk_level: "low",
        accepted: true,
        timestamp: secMinutesAgo(2880),
        created_at: isoMinutesAgo(2880),
        image_url: thumbOk,
        metadata: { source: "demo_fixture", model: "demo-stub", image_url: thumbOk },
      },
      {
        id: "demo-scan-007",
        scan_id: "demo-scan-007",
        plant_id: "cucumber_001",
        zone_id: SESSION_ZONE,
        device_id: SESSION_DEVICE,
        disease: "Healthy",
        confidence: 0.92,
        status: "PASS",
        health_score: 87,
        risk_level: "low",
        accepted: true,
        timestamp: secMinutesAgo(4320),
        created_at: isoMinutesAgo(4320),
        image_url: thumbOk,
        metadata: { source: "demo_fixture", model: "demo-stub", image_url: thumbOk },
      },
    ].slice(0, max);
    return {
      source: "demo",
      total: base.length,
      zone: null,
      status_filter: null,
      scans: base,
    };
  }

  function zoneScanCounts() {
    return {
      source: "demo",
      zones: [
        { zone_id: "zone_alpha", name: "Zone Alpha", total: 2, pass: 1, warn: 1, critical: 0 },
        { zone_id: "zone_beta", name: "Zone Beta", total: 1, pass: 0, warn: 1, critical: 0 },
        { zone_id: "zone_gamma", name: "Zone Gamma", total: 1, pass: 0, warn: 0, critical: 1 },
      ],
    };
  }

  function plantProfile(plantId) {
    const pid = plantId || "cucumber_001";
    return {
      plant_id: pid,
      species_id: "cucumber",
      common_name: "Cucumber",
      scientific_name: "Cucumis sativus",
      family: "Cucurbitaceae",
      latest_scan: scanHistory(1).scans[0],
      scan_count: 4,
      first_seen: isoMinutesAgo(1440 * 14),
      last_seen: isoMinutesAgo(3),
      history: scanHistory(5).scans.filter((s) => s.plant_id === pid).slice(0, 3),
      source: "demo",
    };
  }

  function analyticsSummary() {
    return {
      source: "demo",
      totals: { scans: 5, healthy: 2, warning: 2, critical: 1, pending: 0 },
      avg_confidence: 0.794,
      pass_rate: 0.4,
      last_scan_at: isoMinutesAgo(3),
      zones: 3,
      devices: 3,
      // a couple of duplicate keys used by various dashboard panels
      healthy: 2,
      warning: 2,
      critical: 1,
    };
  }

  function predictPlantImage() {
    const healthy = isHealthy();
    const thumb = _leafThumbDataUri(healthy ? "healthy" : "warning");
    // Phase E — embed a sensor snapshot in metadata so the new
    // result-card Environment section renders real values in Demo Mode
    // instead of "—" everywhere. Mirrors the live sensor fixture exactly
    // so the modal's reading agrees with the home dashboard.
    const _snap = sensorReading();
    return {
      user_id: SESSION_USER,
      zone_id: SESSION_ZONE,
      device_id: SESSION_DEVICE,
      plant_id: "cucumber_001",
      plant_name: "Cucumber",
      disease: healthy ? "Healthy" : "Powdery Mildew",
      disease_class_name: healthy ? "healthy" : "powdery_mildew",
      disease_type: healthy ? "none" : "fungal",
      confidence: healthy ? 0.96 : 0.78,
      accepted: true,
      inference_ms: 124.0,
      // Phase B — honest label. The MVP no longer surfaces this in the
      // user-facing result modal, but Demo Mode still has to put SOMETHING
      // here for analytics / events / debug overlays that read it.
      model_name: "AI Plant Analysis (demo)",
      model_version: "demo-1",
      timestamp: nowIso(),
      plant: {
        species_id: "cucumber",
        common_name: "Cucumber",
        scientific_name: "Cucumis sativus",
        family: "Cucurbitaceae",
        confidence: 0.85,
        source: "demo",
      },
      health: plantHealth(),
      metadata: {
        source: "demo_fixture",
        image_url: thumb,
        scenario: scenario(),
        sensor_snapshot: {
          air_temperature: _snap.air_temperature,
          air_humidity:    _snap.air_humidity,
          light_lux:       _snap.light_lux,
          soil_humidity:   _snap.soil_humidity,
          soil_ph:         _snap.soil_ph,
          soil_ec:         _snap.soil_ec,
        },
      },
    };
  }

  function unifiedReport(plantId) {
    const pid = plantId || "cucumber_001";
    const healthy = isHealthy();
    const health = plantHealth();
    const sensor = sensorReading();
    const warnings = healthy ? [] : [
      {
        category: "general",
        severity: "warning",
        message: "Powdery mildew detected on lower leaves — increase airflow.",
        target: null,
        current: null,
      },
      {
        category: "humidity",
        severity: "warning",
        message: "Humidity 62% is at the upper edge — prefer 50–60% to slow fungal spread.",
        target: "50–60%",
        current: "62%",
      },
    ];
    const careRecs = healthy
      ? [
          {
            category: "watering",
            severity: "info",
            message: "Soil moisture is on target. Hold the current schedule for the next 48h.",
            target: "Soil moisture 50–70%",
            current: "62%",
          },
          {
            category: "sunlight",
            severity: "info",
            message: "Light is ideal for fruiting cucumber — no change needed.",
            target: "20,000–35,000 lux",
            current: "30,000 lux",
          },
        ]
      : [
          {
            category: "watering",
            severity: "advice",
            message: "Water early in the morning to avoid prolonged leaf wetness.",
            target: "Soil moisture 50–70%",
            current: "55%",
          },
          {
            category: "sunlight",
            severity: "info",
            message: "Light levels are inside target for fruiting cucumber.",
            target: "20,000–35,000 lux",
            current: "28,000 lux",
          },
        ];

    return {
      plant_id: pid,
      user_id: SESSION_USER,
      zone_id: SESSION_ZONE,
      device_id: SESSION_DEVICE,
      plant_name: "Cucumber",
      scientific_name: "Cucumis sativus",
      family: "Cucurbitaceae",
      plant: {
        species_id: "cucumber",
        common_name: "Cucumber",
        scientific_name: "Cucumis sativus",
        family: "Cucurbitaceae",
        confidence: 0.85,
        source: "demo",
      },
      disease: healthy ? "Healthy" : "Powdery Mildew",
      disease_class_name: healthy ? "healthy" : "powdery_mildew",
      disease_type: healthy ? "none" : "fungal",
      confidence: healthy ? 0.96 : 0.78,
      accepted: true,
      model_name: "AI Plant Analysis (demo)",
      model_version: "demo-1",
      scores: healthy
        ? { plant_health: 92, disease_risk: 8, stress_level: 6, survival_chance: 96 }
        : { plant_health: 72, disease_risk: 38, stress_level: 22, survival_chance: 68 },
      explanation: healthy
        ? {
            plant_health: "Cucumber is thriving — leaves are uniformly green and no visible lesions.",
            disease_risk: "Low fungal pressure. Humidity and airflow are inside target.",
            stress_level: "Environment is stable. Soil moisture, light, and pH are all green.",
            survival_chance: "Survival is very likely. Maintain current care schedule.",
          }
        : {
            plant_health: "Cucumber is showing mild stress with early powdery mildew on lower leaves.",
            disease_risk: "Moderate risk — fungal pressure rising from cool nights + high humidity.",
            stress_level: "Environmental stress is low. Light and soil moisture are inside target.",
            survival_chance: "Survival likely with airflow + targeted treatment in 24–48h.",
          },
      health: health,
      sensor_data: sensor,
      sensor_freshness: "live",
      care_recommendations: careRecs,
      warnings: warnings,
      care_plan: null,
      current_growth_stage: "fruiting",
      analysis_summary: healthy
        ? "Cucumber is healthy and on track. Sensors are green and no disease detected. Hold current schedule."
        : "Cucumber is mostly healthy but showing early powdery mildew. " +
          "Sensors look good; humidity is at the upper end. " +
          "Reduce overhead watering and treat with a mild antifungal within 48h.",
      timings_ms: { vision_ms: 120.0, plant_id_ms: 6.5, report_ms: 134.7 },
      metadata: { source: "demo_fixture", scenario: scenario() },
    };
  }

  // ------------------------------------------------------------------
  // Public API
  // ------------------------------------------------------------------
  window.plantDemo = {
    isOn,
    setOn,
    toggle,
    scenario,
    setScenario,
    isHealthy,
    storageKey: STORAGE_KEY,
    scenarioKey: SCENARIO_KEY,
    fixtures: {
      sensorLatestEnvelope,   // /sensor/latest
      sensorReading,
      plantHealth,            // /health/plant
      scanHistory,            // /scans/history
      zoneScanCounts,         // /scans/zone-counts
      plantProfile,           // /scans/plant/{id}
      analyticsSummary,       // /analytics/summary
      predictPlantImage,      // /predict
      unifiedReport,          // /report
    },
  };
})();
