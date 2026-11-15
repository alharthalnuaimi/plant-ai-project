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

## Gemini API key (required for AI features)

All AI (photo diagnosis and reasoning) runs on Google Gemini. No model
weights are needed. Create a key at https://aistudio.google.com/app/apikey
and put it in the repo-root `.env` (copied from `.env.example`):

```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash
```

The key stays on the server. Without it the API still starts, but
`/predict`, `/chat`, `/analyze` and image `/report` return HTTP 503
`gemini_not_configured`. See `docs/architecture/gemini-migration.md`.

## Start the server

### CMD (recommended on Windows)

```cmd
cd /d D:\plant-ai-project\backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### PowerShell (optional)

```powershell
cd D:\plant-ai-project\backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The startup log shows `AI: Google Gemini LIVE (...)` when the key is set.

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
6. **GET /health/services** — `gemini_status: live`, `yolo_status: disabled`.
7. **POST /predict** with an image file — Gemini diagnosis, the scan path used by the frontend.
8. **POST /report** with the same image — unified plant report (vision + plant ID + sensor + care + scores).
9. **GET /care/cucumber_001** — sensor-aware care plan.
10. **GET /analytics/summary** and **GET /scans/history** — live data after a scan.

When `PERSISTENCE_BACKEND=postgres` (recommended) data is persisted to
Supabase and survives restarts. When the DB is unreachable the backend
automatically falls back to an in-memory cache so the demo keeps working.

## Tests

From the repo root (any working directory):

```powershell
$env:PERSISTENCE_BACKEND='memory'
python -m pytest -q
```

The suite is self-contained (no Supabase / Docker / network required).
Gemini is replaced by a fake SDK (`backend/tests/gemini_fakes.py`), so no
API quota is used. An optional live check runs only when you opt in:

```powershell
$env:RUN_GEMINI_LIVE_TESTS='1'; python -m pytest backend/tests/test_gemini_live.py -q
``` See `PHASE3.md` for marker breakdown (`unit`, `smoke`, `db`).
