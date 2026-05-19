# Backend setup

FastAPI lives in `backend/`. It serves vision (`/predict`), sensors (`/sensor`), analytics (`/analytics/*`), survival, and health checks.

## Prerequisites

- Python 3.10+
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
2. **POST /sensor** with sample JSON (see `docs/setup_sensors.md`).
3. **GET /sensor/latest** — should return the reading you just posted.
4. **POST /predict** with an image file — scan path used by the frontend.
5. **GET /analytics/summary** and **GET /analytics/history** — should show live data after a scan.

Sensor and analytics data are stored **in memory** for the MVP (resets when the server restarts). No database required yet.
