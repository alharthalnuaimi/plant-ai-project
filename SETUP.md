# PlantVision Setup Guide

How to configure and run the backend and frontend locally. All AI —
plant photo diagnosis and plant-care reasoning — runs on the **Google
Gemini API**. No local model weights, GPU, `ultralytics` or Ollama are
needed.

## 1. Get a Gemini API key

1. Open Google AI Studio: https://aistudio.google.com/app/apikey
2. Sign in and click **Create API key**.
3. Copy the key. Treat it like a password.

Official docs: https://ai.google.dev/gemini-api/docs/api-key

## 2. Environment variables

Copy `.env.example` to `.env` in the repository root:

```bash
cp .env.example .env
```

Set at least:

```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.5-flash
PERSISTENCE_BACKEND=memory   # or postgres + DATABASE_URL for Supabase
STORAGE_BACKEND=local        # or supabase
```

- `GEMINI_API_KEY` is read **only by the backend**. Never put it in
  `frontend/`, `env.js`, Vercel public variables or browser storage.
  `.env` is git-ignored.
- `GEMINI_DIAGNOSIS_MODEL` / `GEMINI_REASONING_MODEL` let you use a
  different model for each step; both default to `GEMINI_MODEL`.
- Timeouts, retries, image size limits and the diagnosis cache are
  documented in `.env.example`.

On Railway / other hosts, set the same variables in the service's
environment settings instead of a `.env` file.

## 3. Install dependencies

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows  (source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
```

For running tests: `pip install -r requirements-dev.txt`.

## 4. Start the backend

```bash
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The startup log prints `AI: Google Gemini LIVE (diagnosis=..., reasoning=...)`.
If it warns that `GEMINI_API_KEY is not set`, the server still runs but
the AI routes answer HTTP 503 `gemini_not_configured`.

Check: http://127.0.0.1:8000/health/services → `"gemini_status": "live"`,
`"yolo_status": "disabled"`.

## 5. Start the frontend

```bash
cd frontend/mobile-app
node server.js
```

Open http://localhost:3000. On `localhost` the frontend talks to
`http://localhost:8000`; override with `?api=http://HOST:8000`.

## 6. How it works

- **Diagnosis** (`POST /predict`, also used by `/analyze` and image `/report`):
  the photo is validated, EXIF-rotated, downscaled and re-encoded as JPEG,
  then sent to Gemini with a strict JSON schema. Gemini reports image
  quality, the species, visible symptoms (each marked *confirmed* or
  *possible*), a primary diagnosis only when the evidence supports it,
  alternatives and uncertainties. The response keeps the existing
  `VisionResult` shape; the full assessment is in `metadata.gemini_diagnosis`.
- **Reasoning** (`POST /chat`, second step of `/analyze`): Gemini receives
  the diagnosis, every available sensor reading (air/soil temperature,
  humidity, soil moisture, pH, EC, light) with its age, the rule-based
  survival score and the user's question, and returns a structured
  explanation, treatment plan, urgency and (only when justified) a
  qualitative recovery outlook.
- The **survival score** is still the deterministic, rule-based score in
  `backend/services/survival.py`.

Details, error codes and troubleshooting: `docs/architecture/gemini-migration.md`.

## 7. Troubleshooting

| Response `error` | Meaning | Fix |
|---|---|---|
| `gemini_not_configured` (503) | No `GEMINI_API_KEY` on the server | Set it and restart |
| `gemini_auth_failed` (502) | Key rejected | Create a new key in AI Studio; check for stray spaces/quotes |
| `gemini_quota_exceeded` (429) | Daily/billing quota used up | Wait for the reset or enable billing — https://ai.google.dev/gemini-api/docs/rate-limits |
| `gemini_rate_limited` (429) | Per-minute limit hit (already retried) | Retry shortly; lower request rate |
| `gemini_timeout` (504) / `gemini_unavailable` (503) / `gemini_network_error` (503) | Transient; already retried with backoff | Retry; raise `GEMINI_TIMEOUT_SECONDS`; check outbound network |
| `gemini_invalid_response` (502) | Gemini's answer failed schema validation or was cut off | Retry; raise `GEMINI_MAX_OUTPUT_TOKENS` |
| `gemini_safety_blocked` (422) | Gemini declined the request | Use a different photo |
| `invalid_image` (400) / `image_too_large` (413) | Unreadable, tiny or oversized upload | Upload a JPEG/PNG/WebP under `MAX_UPLOAD_BYTES` |

Official troubleshooting guide: https://ai.google.dev/gemini-api/docs/troubleshooting

## 8. Legacy YOLO models (disabled)

The YOLOv8 per-species router, the Pl@ntNet identifier and the Ollama
narrative code remain in `backend/models/` and the training pipeline in
`training/` and `scripts/` is unchanged, but the running API never loads
them. Weights under `artifacts/models/` are only needed if you run the
training or evaluation scripts.
