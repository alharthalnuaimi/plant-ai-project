/**
 * FastAPI backend base URL for Plant AI /predict integration.
 *
 * Override (no code change):
 * - URL query: ?api=http://10.0.2.2:8000  (Android emulator browser)
 * - localStorage: pv-api-base = http://YOUR_PC_IP:8000  (phone on Wi-Fi)
 *
 * Production safety:
 * - env.js (Vercel build or committed default) sets __PLANT_API_URL__
 * - Stale pv-api-base pointing at localhost is ignored on deployed hosts
 * - Vercel / production hosts always fall back to the Railway backend
 */
(function () {
  const RAILWAY_DEFAULT = "https://plant-ai-project-production.up.railway.app";
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("api");
  let fromStorage = localStorage.getItem("pv-api-base");
  const host = window.location.hostname;
  const isLocalHost = host === "localhost" || host === "127.0.0.1";
  const isDeployedHost = /\.vercel\.app$/i.test(host) || /\.railway\.app$/i.test(host);

  // A leftover localhost override breaks scans/chat on the live Vercel site.
  if (fromStorage && !isLocalHost && /localhost|127\.0\.0\.1/i.test(fromStorage)) {
    fromStorage = null;
  }

  let base = (fromQuery || fromStorage || "").trim();
  if (!base) {
    if (window.__PLANT_API_URL__) {
      base = window.__PLANT_API_URL__;
    } else if (isLocalHost || isDeployedHost) {
      base = RAILWAY_DEFAULT;
    } else {
      // LAN static server on phone → backend on same machine IP :8000
      base = `http://${host}:8000`;
    }
  }
  window.PLANT_API_BASE = base.replace(/\/$/, "");

  const fromStorageUser = localStorage.getItem("pv-user-id");
  const fromQueryUser = params.get("user");
  let userId = (fromQueryUser || fromStorageUser || "demo_user").trim();
  if (!userId) userId = "demo_user";
  window.PLANT_USER_ID = userId;

  const fromStorageZone = localStorage.getItem("pv-zone-id");
  const fromQueryZone = params.get("zone");
  let zoneId = (fromQueryZone || fromStorageZone || "zone_alpha").trim();
  if (!zoneId) zoneId = "zone_alpha";
  window.PLANT_ZONE_ID = zoneId;

  const fromStorageDevice = localStorage.getItem("pv-device-id");
  const fromQueryDevice = params.get("device");
  let deviceId = (fromQueryDevice || fromStorageDevice || "esp32_001").trim();
  if (!deviceId) deviceId = "esp32_001";
  window.PLANT_DEVICE_ID = deviceId;
})();
