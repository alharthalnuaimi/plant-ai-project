# Frontend setup

The mobile/web UI is in `frontend/mobile-app/` (vanilla HTML/CSS/JS + optional Node static server).

## Prerequisites

- FastAPI backend running (see `docs/setup_backend.md`)
- Node.js (for `server.js`) or any static file server

## API URL

Default: `http://127.0.0.1:8000` in `frontend/mobile-app/config.js`.

| Scenario | API base URL |
|----------|----------------|
| PC browser | `http://127.0.0.1:8000` |
| Phone on Wi-Fi | `http://YOUR_PC_LAN_IP:8000` |
| Android emulator | `http://10.0.2.2:8000` |

Override without editing files:

- Query string: `http://localhost:3000/?api=http://192.168.1.10:8000`
- Console: `localStorage.setItem('pv-api-base','http://192.168.1.10:8000'); location.reload()`

## User and zone IDs (scan + API)

Defaults in `config.js`:

- `PLANT_USER_ID` → `demo_user` (override: `?user=my_id` or `localStorage pv-user-id`)
- `PLANT_ZONE_ID` → `zone_alpha` (override: `?zone=zone_beta` or `localStorage pv-zone-id`)
- `PLANT_DEVICE_ID` → `esp32_001` (override: `?device=esp32_002` or `localStorage pv-device-id`)

**POST /predict** sends `user_id` and `zone_id` only (scan is per user + zone).

**GET /sensor/latest** sends all three query params so the env panel matches the correct device.

## Start the frontend

### CMD (recommended on Windows)

```cmd
cd /d D:\plant-ai-project\frontend\mobile-app
node server.js
```

### PowerShell (optional)

```powershell
cd D:\plant-ai-project\frontend\mobile-app
node server.js
```

Open http://localhost:3000 (or http://YOUR_PC_IP:3000 from a phone on the same network).

## Test scan (unchanged MVP flow)

1. Confirm backend `/health` is OK.
2. Open the app → Home → scan (center button).
3. Pick a cucumber leaf image.
4. Modal shows disease, confidence, accepted, inference time from **POST /predict**.

## Test analytics dashboard

1. After a scan, open **Data** — metrics and scan history should update immediately (not only after 5s).
2. Header should show **● Live** when real scans exist; **● Demo** before the first scan.
3. **POST /sensor** (see `docs/setup_sensors.md`) — zone cards and event feed update without flicker.

## Test environment panel

1. With backend running, POST sample sensor data (see `docs/setup_sensors.md`).
2. Reload or wait ~5s — Home environment strip polls **GET /sensor/latest**.
3. Air temperature, air humidity, light (lux), and soil humidity update from live data.
4. If no sensor POST yet, the strip shows demo fallback values.

More detail: `frontend/README.md`.
