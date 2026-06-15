# Backend setup

FastAPI lives in `backend/`. It serves vision (`/predict`), sensors
(`/sensor`), analytics (`/analytics/*`), care recommendations (`/care/*`),
the unified plant report (`/report`), scan history (`/scans/*`),
survival, and health checks.

> For Supabase Cloud persistence (recommended), see `SETUP_PHASE2.md`.
> For the audit log + retry telemetry layered on top, see `PHASE3.md`.

## Prerequisites

- Python 3.11+
- Virtual environment (recommended)

### CMD (Windows)

```cmd
cd /d D:\plant-ai-project\backend
python -m venv .venv
.\.venv\Scripts\activate.bat
pip install -r requirements.txt
```

### PowerShell (optional)

```powershell
cd D:\plant-ai-project\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## YOLO weights

Point the API at your trained cucumber model.

### CMD

```cmd
set YOLO_WEIGHTS_PATH=D:\plant-ai-project\artifacts\models\cucumber_yolov8.pt
```

### PowerShell (optional)

```powershell
$env:YOLO_WEIGHTS_PATH = "D:\plant-ai-project\artifacts\models\cucumber_yolov8.pt"
```

Default path (if unset) is resolved relative to the project root under `artifacts/models/`.

## Start the server

### CMD (recommended on Windows)

```cmd
set YOLO_WEIGHTS_PATH=D:\plant-ai-project\artifacts\models\cucumber_yolov8.pt
cd /d D:\plant-ai-project\backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### PowerShell (optional)

```powershell
$env:YOLO_WEIGHTS_PATH = "D:\plant-ai-project\artifacts\models\cucumber_yolov8.pt"
cd D:\plant-ai-project\backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- API base: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health: http://127.0.0.1:8000/health

Use `--host 0.0.0.0` so phones and ESP32 on the same LAN can reach the API.

## Quick checks

1. Open `/docs` and call **GET /health**.
2. **GET /health/db** — `supabase_cloud_connected` when wired, `memory_fallback` otherwise.
3. **POST /sensor** with sample JSON (see `docs/setup_sensors.md`).
4. **GET /sensor/latest** — should return the reading you just posted.
5. **GET /health/sensor** — per-device freshness + retry telemetry.
6. **POST /predict** with an image file — scan path used by the frontend.
7. **POST /report** with the same image — unified plant report (vision + plant ID + sensor + care + scores).
8. **GET /care/cucumber_001** — sensor-aware care plan.
9. **GET /analytics/summary** and **GET /scans/history** — live data after a scan.

When `PERSISTENCE_BACKEND=postgres` (recommended) data is persisted to
Supabase and survives restarts. When the DB is unreachable the backend
automatically falls back to an in-memory cache so the demo keeps working.

## Tests

From the repo root (any working directory):

```powershell
$env:PERSISTENCE_BACKEND='memory'
python -m pytest -q
```

The suite is self-contained (no Supabase / Docker required) and runs in
about a second. See `PHASE3.md` for marker breakdown (`unit`, `smoke`, `db`).
