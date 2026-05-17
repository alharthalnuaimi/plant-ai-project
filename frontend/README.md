# Frontend — Plant AI integration

## Layout

```text
frontend/
├── _imports/          # Raw ZIP from teammates (plant-MB-main.zip)
└── mobile-app/        # Extracted PlantVision web app
    ├── config.js      # FastAPI base URL
    ├── api.js         # POST /predict client
    ├── app.js         # UI logic (scan wired to backend)
    ├── index.html
    └── server.js      # Optional Node static server (port 3000)
```

## Detected framework

**Vanilla HTML / CSS / JavaScript** with a small **Node.js** static server (`server.js`).  
Not React Native, Flutter, or Expo — runs in the browser (desktop or mobile).

## Prerequisites

1. **FastAPI backend running** with YOLO weights:

```powershell
$env:YOLO_WEIGHTS_PATH = "D:\plant-ai-project\artifacts\models\cucumber_yolov8.pt"
cd D:\plant-ai-project\backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

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

```bash
cd D:\plant-ai-project\frontend\mobile-app
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

## API contract (MVP)

```http
POST /predict
Content-Type: multipart/form-data
Field: file  (image)
```

Response (example):

```json
{
  "disease": "diseased",
  "confidence": 0.9832,
  "accepted": true,
  "inference_ms": 3925.81,
  "model_name": "yolov8"
}
```

Only `/predict` is integrated. Sensors, Ollama, survival, and `/analyze` are not used in this MVP frontend pass.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `API offline` in header | Start uvicorn; check firewall allows port 8000 |
| CORS error | Backend already allows `*` origins in MVP |
| Scan failed on phone | Set `pv-api-base` to PC LAN IP, not `127.0.0.1` |
| Slow first scan | YOLO model loads on first request (~3–5 s) |
