/**
 * FastAPI backend base URL for Plant AI /predict integration.
 *
 * Override (no code change):
 * - URL query: ?api=http://10.0.2.2:8000  (Android emulator browser)
 * - localStorage: pv-api-base = http://YOUR_PC_IP:8000  (phone on Wi-Fi)
 */
(function () {
  const params = new URLSearchParams(window.location.search);
  const fromQuery = params.get("api");
  const fromStorage = localStorage.getItem("pv-api-base");
  const host = window.location.hostname;

  let base = (fromQuery || fromStorage || "").trim();
  if (!base) {
    if (host === "localhost" || host === "127.0.0.1") {
      base = "http://127.0.0.1:8000";
    } else {
      // e.g. phone opens http://192.168.1.5:3000 → API on same IP :8000
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
