# Frontend — Plant AI integration

## Layout

```text
frontend/
└── mobile-app/        # PlantVision web app (vanilla HTML/CSS/JS)
    ├── config.js      # FastAPI base URL + user/zone/device IDs
    ├── env.js         # Optional public backend URL override
    ├── api.js         # Backend client (predict, sensor, scans, care, report, …)
    ├── app.js         # Core UI logic, navigation, persistence
    ├── home.js        # Home dashboard panels
    ├── analytics.js   # Data / scan history dashboard
    ├── garden.js      # Garden map + zone management
    ├── profile.js     # Profile + settings panes
    ├── assistant.js   # Floating AI chat widget
    ├── settings.js    # Settings page wiring
    ├── style.css      # Full design system
    ├── index.html     # Single-page app shell
    └── server.js      # Optional Node static server (port 3000)
```

> `frontend/_imports/` is git-ignored and only used for ad-hoc developer
> drops of upstream ZIPs; nothing in the running app reads from it.

## Detected framework

**Vanilla HTML / CSS / JavaScript** with a small **Node.js** static server (`server.js`).  
Not React Native, Flutter, or Expo — runs in the browser (desktop or mobile).

## Prerequisites

1. **FastAPI backend running** with YOLO weights (CMD on Windows):

```cmd
set YOLO_WEIGHTS_PATH=D:\plant-ai-project\artifacts\models\cucumber_yolov8.pt
cd /d D:\plant-ai-project\backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

PowerShell alternative: `$env:YOLO_WEIGHTS_PATH = "D:\plant-ai-project\artifacts\models\cucumber_yolov8.pt"` then the same `uvicorn` line.

2. Confirm API docs: http://127.0.0.1:8000/docs  
   If this does not open, fix the backend before testing the frontend.

## Set backend API URL

Default (PC browser): `http://127.0.0.1:8000`

| Scenario | API base URL |
|----------|----------------|
| PC / same machine | `http://127.0.0.1:8000` |
| Phone on Wi-Fi | `http://YOUR_PC_LAN_IP:8000` |
| Android emulator browser | `http://10.0.2.2:8000` |

**Override without editing code:**

- URL query: open app as  
  `http://localhost:3000/?api=http://10.0.2.2:8000`
- Or in browser console:  
  `localStorage.setItem('pv-api-base','http://192.168.1.10:8000'); location.reload()`

Config file: `mobile-app/config.js`

## Run frontend

### Option A — Node static server (recommended, same as original project)

```cmd
cd /d D:\plant-ai-project\frontend\mobile-app
node server.js
```

Open: http://localhost:3000  
On phone (same Wi-Fi): http://YOUR_PC_IP:3000

### Option B — Open `index.html` directly

May block `fetch` to another origin (CORS). Prefer Option A or any static server.

## Test image upload → `/predict`

1. Start backend (see above).
2. Start frontend (`node server.js`).
3. Open the app → **Home** → click **scan** (center button or “Initialize Scan”).
4. Choose a cucumber leaf image from gallery/camera.
5. Result modal shows:
   - **Disease** (e.g. `diseased`)
   - **Confidence** (%)
   - **Accepted** (Yes/No)
   - **Inference time** (ms)

Top bar **AI Core** shows `API OK` when `GET /health` succeeds.

## Integrated backend endpoints

The frontend talks to FastAPI via `frontend/mobile-app/api.js`:

| Route                                   | Used by                                       |
|-----------------------------------------|-----------------------------------------------|
| `POST /predict`                         | Home scan modal (disease + plant ID block)    |
| `POST /sensor` / `GET /sensor/latest`   | Live environment strip + sensor cache hydrate |
| `GET /health`, `/health/db`, `/health/sensor` | Sidebar status chip + diagnostics       |
| `GET /analytics/*`, `GET /scans/*`      | Data page (summary, history, zone counts)     |
| `GET /care/{plant_id}`                  | Care recommendations panel                    |
| `POST /report`                          | Unified plant report (multipart + JSON paths) |
| `GET/POST/PUT/DELETE /zones`, `/devices`| Garden map management                         |

Every call is non-blocking and degrades to demo / cached data when the
backend is offline, so the app keeps rendering during outages.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `API offline` in header | Start uvicorn; check firewall allows port 8000 |
| CORS error | Backend already allows `*` origins in MVP |
| Scan failed on phone | Set `pv-api-base` to PC LAN IP, not `127.0.0.1` |
| Slow first scan | YOLO model loads on first request (~3–5 s) |
