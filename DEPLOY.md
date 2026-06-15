# PlantVision — Deployment Guide

This document is the operator runbook for shipping PlantVision to a real,
public URL. It assumes Phase 3 is complete and `python -m pytest -q`
passes locally with **100 / 100**.

---

## 1. Recommended deployment

| Layer        | Platform                  | Why                                                              |
|--------------|---------------------------|------------------------------------------------------------------|
| Frontend     | **Vercel** (static)       | Zero-config static hosting, global CDN, free TLS.                |
| Backend API  | **Railway**               | Already wired (`backend/Procfile` + `backend/railway.toml`), Nixpacks autobuilds Python, `$PORT` binding works out of the box, health-checks the `/health` route. |
| Database     | **Supabase Cloud**        | Already set up in Phase 2 (see [`SETUP_PHASE2.md`](SETUP_PHASE2.md)); the backend talks to it via `DATABASE_URL` over the Transaction Pooler. |
| YOLO weights | Stays on the backend host | Never deployed to Vercel. Stub fallback runs when weights are absent — see [Model strategy](#model-strategy). |

**Pick Railway over Render** for this project. Reasons:

* `backend/Procfile` and `backend/railway.toml` already exist, both
  honour `$PORT` and bind `0.0.0.0`.
* Nixpacks reads `backend/runtime.txt` (`python-3.11`) automatically;
  no `render.yaml` to maintain.
* Health-check path (`/health`) is already wired in `railway.toml`.
* Free plan is generous enough for an MVP demo (sleeps after
  inactivity; cold start is well within the YOLO stub's response time).

Render is a perfectly valid alternative — a starter `render.yaml` is
included in [Appendix A](#appendix-a--render-alternative) if you ever
need to migrate.

---

## 2. Architecture

```mermaid
flowchart LR
    subgraph Client
        Mobile[Mobile browser / PWA]
    end

    subgraph Vercel[Vercel · Global CDN]
        Static[frontend/mobile-app/<br/>HTML · CSS · JS · env.js]
    end

    subgraph Railway[Railway · Nixpacks]
        Uvicorn[uvicorn 0.0.0.0:$PORT]
        FastAPI[FastAPI app<br/>routes + services + repos]
        Stub[Stub vision predictor]
        Yolo[YoloVisionPredictor<br/>optional, on-disk weights]
    end

    subgraph Supabase[Supabase Cloud · Postgres]
        Tables[(sensor_readings · scan_results · zones · devices · audit_log · analytics_events)]
    end

    subgraph Edge
        ESP32[ESP32 sensor node]
    end

    Mobile -- HTTPS --> Static
    Static -- "PLANT_API_BASE<br/>(absolute URL)" --> Uvicorn
    Uvicorn --> FastAPI
    FastAPI -- asyncpg pool · TLS · pgbouncer --> Tables
    FastAPI --> Stub
    FastAPI -. when weights present .-> Yolo
    ESP32 -- "POST /sensor" --> Uvicorn
```

Key invariants the deployment preserves:

* The frontend never talks to Supabase directly — all DB credentials
  live in the backend.
* The backend degrades gracefully: if `DATABASE_URL` is unreachable
  it falls back to in-memory stores instead of crashing.
* CORS defaults to wide-open (`allow_origins=["*"]`) so any Vercel
  preview domain can call the Railway backend without extra config.
  Pin it for production by setting `CORS_ALLOWED_ORIGINS` (Phase 4).

---

## 3. Required environment variables

### 3.1 Backend (Railway)

Mirror these from [`.env.example`](.env.example). Set them in
**Railway → Variables**.

| Variable                       | Required | Default                                  | Purpose                                                                 |
|--------------------------------|----------|------------------------------------------|-------------------------------------------------------------------------|
| `PORT`                         | auto     | injected by Railway                      | Bound by `Procfile` / `railway.toml` — do **not** set manually.         |
| `PERSISTENCE_BACKEND`          | yes      | `postgres`                               | `postgres` = Supabase Cloud; `memory` = no DB (graceful fallback demo). |
| `DATABASE_URL`                 | yes¹     | —                                        | Supabase Transaction Pooler URI (port `6543`).                          |
| `PERSIST_EVENTS`               | no       | `true`                                   | Toggle `analytics_events` writes.                                       |
| `PERSIST_SENSOR_HISTORY`       | no       | `true`                                   | Toggle `sensor_readings` writes.                                        |
| `PERSIST_SCAN_HISTORY`         | no       | `true`                                   | Toggle `scan_results` writes.                                           |
| `YOLO_WEIGHTS_PATH`            | no       | `artifacts/models/cucumber_yolov8.pt`    | Absolute path on the Railway container. Leave unset/empty → stub runs.  |
| `YOLO_CONF`                    | no       | `0.25`                                   | YOLO confidence threshold.                                              |
| `YOLO_IMGSZ`                   | no       | `640`                                    | YOLO inference image size.                                              |
| `MODEL_REGISTRY_PATH`          | no       | `artifacts/registry.json`                | Override only if registry lives outside the repo.                       |
| `MAX_IMAGE_SIDE`               | no       | `1024`                                   | Server-side image downscale before inference.                           |
| `PLANT_ID_MODEL`               | no       | `stub`                                   | Plant-ID backend (`stub` only today; reserved for future seam).         |
| `SURVIVAL_WEIGHT_DISEASE`      | no       | `0.40`                                   | Survival weighting (sum of all four ≈ 1.0).                             |
| `SURVIVAL_WEIGHT_SOIL_MOISTURE`| no       | `0.25`                                   | "                                                                       |
| `SURVIVAL_WEIGHT_TEMPERATURE`  | no       | `0.20`                                   | "                                                                       |
| `SURVIVAL_WEIGHT_HUMIDITY`     | no       | `0.15`                                   | "                                                                       |
| `OLLAMA_BASE_URL`              | no       | empty                                    | Leave empty unless you also run an Ollama sidecar.                      |
| `OLLAMA_MODEL`                 | no       | `llama3.1`                               | Ignored when `OLLAMA_BASE_URL` is empty.                                |
| `CORS_ALLOWED_ORIGINS`         | no       | `*` (wide-open)                          | Phase 4: comma-separated allowlist. **Set this for prod** to your Vercel domain(s), e.g. `https://plantvision.vercel.app,http://localhost:3000`. |

¹ If `PERSISTENCE_BACKEND=memory` you can omit `DATABASE_URL` entirely
(the app boots without any DB and falls back to in-memory stores).

> **Secrets hygiene.** `DATABASE_URL` contains your Supabase password;
> set it via Railway's Variables UI, never commit it. `.env` is
> git-ignored — only `.env.example` is tracked.

### 3.2 Frontend (Vercel)

| Variable          | Required | Example                                       | Purpose                                                                                                                                          |
|-------------------|----------|-----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `PLANT_API_BASE`  | yes      | `https://plantvision-api.up.railway.app`      | Absolute URL of the FastAPI backend. Injected into `mobile-app/env.js` at deploy time by the `buildCommand` in `frontend/vercel.json` (no trailing slash). |

There are no other build-time env vars — the frontend is vanilla
HTML/CSS/JS with no bundler. See
[`frontend/.env.production.example`](frontend/.env.production.example).

---

## 4. Step-by-step deploy

### Step 1 — Supabase Cloud (already done)

The Supabase project, schema, and `DATABASE_URL` are configured in
Phase 2. If you are setting up a fresh Supabase project:

1. Follow [`SETUP_PHASE2.md`](SETUP_PHASE2.md) §3–§5 to create the
   project, apply migrations `0001_init.sql` and `0002_seed.sql`, and
   grab the Transaction Pooler URI.
2. Apply the Phase 3 audit-log migration:
   ```powershell
   python scripts/apply_migration_0003.py
   ```
3. Save the pooler URI as `DATABASE_URL` — you'll paste it into
   Railway in Step 2.

### Step 2 — Deploy the backend to Railway

1. Push the repo to GitHub (if not already there).
2. Go to <https://railway.app> → **New Project** → **Deploy from GitHub
   repo** → pick the PlantVision repo.
3. Railway auto-detects Nixpacks. Open **Settings → Service** and set:
   * **Root Directory:** `backend`
   * **Start Command:** _leave blank_ (Procfile/railway.toml win).
   * **Health Check Path:** `/health` (already set by `railway.toml`).
4. Open **Variables** and paste in every required row from
   [§3.1](#31-backend-railway). Minimum to start:
   ```env
   PERSISTENCE_BACKEND=postgres
   DATABASE_URL=postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres
   PERSIST_EVENTS=true
   PERSIST_SENSOR_HISTORY=true
   PERSIST_SCAN_HISTORY=true
   ```
5. **Deploy**. First build takes ~2–3 minutes. When green, click
   **Settings → Networking → Generate Domain** to mint
   `https://<service>.up.railway.app`. **Copy that URL** — you need it
   in Step 4.

### Step 3 — Deploy the frontend to Vercel

1. Go to <https://vercel.com> → **Add New… → Project** → import the
   same GitHub repo.
2. In the import wizard set:
   * **Root Directory:** `frontend`
   * **Framework Preset:** _Other_ (Vercel will pick this up from
     `frontend/vercel.json` automatically).
   * Leave **Build Command** and **Output Directory** blank — they are
     read from `frontend/vercel.json`.
3. Click **Deploy** (without any env vars yet). The first build will
   succeed but the frontend will not yet know where the backend is —
   that's fixed in Step 4.

### Step 4 — Wire the frontend to the backend

1. Vercel → Project → **Settings → Environment Variables** → add:
   * `PLANT_API_BASE` = `https://<your-railway-service>.up.railway.app`
     (no trailing slash). Apply to **Production** (and optionally
     Preview).
2. Vercel → **Deployments** → on the latest deployment, click the
   "⋯" menu → **Redeploy**. The `buildCommand` in `vercel.json`
   rewrites `mobile-app/env.js` to embed the new URL.
3. Open the production URL in a browser, open DevTools console, run:
   ```js
   window.PLANT_API_BASE
   // → "https://<your-railway-service>.up.railway.app"
   ```
   That confirms the wiring.

### Step 5 — Smoke-test the deployment

See [§5](#5-post-deploy-verification).

---

## 5. Post-deploy verification

Run these from any shell once both services are live. Replace
`https://api.example.com` with your Railway domain.

```bash
# Liveness
curl -s https://api.example.com/health
# expected: {"status":"ok","uptime_sec":<n>}

# Supabase connectivity
curl -s https://api.example.com/health/db
# expected: status="supabase_cloud_connected", deployment="cloud"

# Sensor pipeline + retry telemetry
curl -s https://api.example.com/health/sensor
# expected: status in {"healthy","degraded","offline"}, "postgres_reachable": true

# Audit-log tail (DB-backed when Supabase is reachable)
curl -s "https://api.example.com/health/audit?limit=5"
# expected: {"count": <n>, "events": [...]}

# Round-trip a sensor reading (no auth — same payload an ESP32 sends)
curl -s -X POST https://api.example.com/sensor \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "demo_user",
    "zone_id": "zone_alpha",
    "device_id": "esp32_smoke_test",
    "air_temperature": 24.0,
    "air_humidity": 60.0,
    "light_lux": 28000.0,
    "soil_temperature": 22.0,
    "soil_humidity": 65.0,
    "soil_ph": 6.4,
    "soil_ec": 2.0
  }'
# expected: HTTP 200 with the persisted/normalised reading echoed back.

# Read it back
curl -s "https://api.example.com/sensor/latest?user_id=demo_user&zone_id=zone_alpha&device_id=esp32_smoke_test"
# expected: { "source": "live", "reading": { ..the row you just posted.. } }
```

PowerShell equivalents (Windows):

```powershell
Invoke-RestMethod "$env:API/health"
Invoke-RestMethod "$env:API/health/db"
Invoke-RestMethod -Method POST -Uri "$env:API/sensor" -ContentType "application/json" `
  -Body (@{
    user_id="demo_user"; zone_id="zone_alpha"; device_id="esp32_smoke_test";
    air_temperature=24.0; air_humidity=60.0; light_lux=28000.0;
    soil_temperature=22.0; soil_humidity=65.0; soil_ph=6.4; soil_ec=2.0
  } | ConvertTo-Json)
```

In the browser:

1. Open `https://<your-vercel>.vercel.app/` — the dashboard renders.
2. DevTools → **Network**: confirm requests go to your Railway URL
   (not `localhost:8000`).
3. Trigger a scan from the Home page — the result modal should show
   a disease label, confidence, and the saved scan thumbnail.
4. Home → **Sensors** card should show `live` or `stale` (not `offline`)
   within ~30 s of the smoke-test sensor post above.

---

## 6. Model strategy

The default deployment runs with **no YOLO weights**. The stub
predictor (`StubVisionPredictor`) is bundled with the code, always
loads, and returns a deterministic disease label + confidence for the
demo path. `/predict` will never 500 because of missing weights.

### Option A — Stub-only (default, recommended for MVP demo)

* Nothing to do. `YOLO_WEIGHTS_PATH` either points to a path that
  does not exist on the Railway container (the default
  `artifacts/models/cucumber_yolov8.pt` is git-ignored), or is left
  empty. The model resolver logs a warning and falls back to stub.
* `GET /models/health` will report `vision_version: "stub"`.

### Option B — Real YOLOv8 weights (future)

When you want the real model in production:

1. Upload weights to a Railway **Volume** mounted at
   `/data/models/cucumber_yolov8.pt`.
2. Set `YOLO_WEIGHTS_PATH=/data/models/cucumber_yolov8.pt` in Railway
   Variables.
3. Uncomment `ultralytics>=8.0.0` in `backend/requirements.txt` and
   redeploy.
4. Confirm via `GET /models/registry` that `weights_path` is the
   volume path and `source` is `env`.

Alternatively, on Render use a **Disk** attachment with the same
strategy. We do not recommend baking weights into the container image
(they're large and the Vercel/Railway free tiers have build-size
limits).

---

## 7. Deployment checklist (cut-and-paste)

Before announcing the demo URL, walk this list:

- [ ] `python -m pytest -q` passes locally (**131 / 131** as of Phase Final).
- [ ] Railway service is **active**, build log green, latest deploy
      shows `uvicorn running on http://0.0.0.0:$PORT`.
- [ ] `GET /health` returns `200 {status:"ok"}`.
- [ ] `GET /health/db` returns `status:"supabase_cloud_connected"`.
- [ ] `GET /health/sensor` returns `status` in `{healthy, degraded}`
      (not `offline` if you've sent any reading).
- [ ] `GET /health/audit?limit=5` returns at least one row (it will
      include startup events once you've done any sensor write).
- [ ] Vercel deployment is **Ready**, URL opens the dashboard, DevTools
      shows requests routed to the Railway URL.
- [ ] `window.PLANT_API_BASE` in DevTools matches the Railway URL.
- [ ] `POST /sensor` round-trip from the smoke-test payload above works.
- [ ] A scan upload returns a JSON result and the thumbnail renders.
- [ ] Railway → **Variables** does **not** contain plaintext copies of
      your Supabase password in any other field besides
      `DATABASE_URL`.

---

## 7.1 Pre-submission checklist (July 1 — graduation demo)

Run this list the **day before** the demo and again **two hours before**:

- [ ] `cd backend; python -m pytest -q` — confirm **131 passed** (Phase Final
      baseline). No skipped, no failed.
- [ ] `git status` clean (no uncommitted experimental files).
- [ ] `git pull` on the laptop you will demo from (so you have the
      latest README / DEPLOY / PHASE_FINAL).
- [ ] Run the **Manual test checklist** in `PHASE_FINAL.md §Manual test
      checklist` end-to-end (10 steps, ~3 minutes).
- [ ] Open the live frontend URL — verify the topbar **system online**
      chip is green and the offline banner is **hidden**.
- [ ] Open Settings → Demo Mode — verify the toggle works and the
      **DEMO** chip lights up amber when enabled.
- [ ] Take all required screenshots — see `PHASE_FINAL.md §Screenshots
      checklist`.
- [ ] Confirm at least 3 sample scan results are present in the live
      `scan_results` table (so the Home log is non-empty during the demo).
- [ ] Confirm at least one sensor reading from the last hour
      (`GET /health/sensor` → freshness < 30s).
- [ ] Backup plan ready: Demo Mode toggled OFF beforehand, but the
      laptop knows where the toggle lives (Settings → Demo Mode) in
      case the backend cold-starts mid-demo.

---

## 7.2 If the live demo fails — fall back to Demo Mode

PlantVision ships with a **frontend-only Demo Mode** specifically for
the graduation demo so a backend outage never sinks the presentation.

When to use it:

* Railway free-tier cold-start exceeds the audience's patience.
* Supabase is unreachable, key was rotated, or the pooler is rate-limiting.
* The conference room WiFi blocks outbound HTTPS to your Railway domain.
* The ESP32 is unplugged / out of WiFi range and you still want to show
  the dashboard reacting to "live" sensor data.

How to enable mid-demo (≈ 5 seconds):

1. Navigate to **Settings** in the frontend (bottom-right icon).
2. Scroll to the **DEMO MODE** card.
3. Toggle the switch **ON**. The topbar shows an amber **DEMO** chip.
4. (Optional) Change **Scenario** to `Powdery mildew (warning)` for the
   richer story or `Thriving cucumber (healthy)` for the clean story.
5. Navigate back to Home — dashboard immediately populates from canned
   fixtures (`frontend/mobile-app/demo_fixtures.js`).

What still works in Demo Mode:

* Hero plant-health ring, warnings strip, care card, sensor KPI cards.
* Scan log with 5–7 realistic entries and SVG leaf thumbnails.
* Health-trend Chart.js graph (last 7 demo scans).
* `POST /predict` is short-circuited — the result modal still populates.
* All navigation, modals, and toasts.

What does NOT work in Demo Mode (and that's fine):

* Live Supabase persistence (nothing is written).
* Real ESP32 sensor readings (canned values used instead).
* Real YOLO inference (the demo stub label is shown).

When the backend comes back, toggle Demo Mode **OFF** and the frontend
resumes hitting Railway exactly as before.

---

## 8. Risks & known limitations

| Risk                                                                              | Impact                                                          | Mitigation                                                                                       |
|-----------------------------------------------------------------------------------|-----------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| `frontend/mobile-app/server.js` (`/api/data`, `/api/geocode`, `/api/poi`) is **not** on Vercel | Cross-device profile sync + map search/POI lookup degrade silently. | Documented. App keeps working via localStorage. If needed later, move those endpoints into FastAPI or a Vercel serverless function. |
| Railway free plan **sleeps** after inactivity                                     | First request after idle has ~10–20 s cold start.               | For demo only. Upgrade to Starter plan if a snappy first response matters.                       |
| Supabase Transaction Pooler (port 6543) blocks named prepared statements          | Some asyncpg patterns 500 if you wire them in later.            | Already handled in `backend/db/connection.py` (`statement_cache_size=0`, `jit: off`).            |
| YOLO weights **not** shipped to Railway by default                                | `/predict` uses the stub label — fine for demo, not real diagnosis. | See [Option B](#option-b--real-yolov8-weights-future) when you're ready for real weights.        |
| Wide-open CORS when `CORS_ALLOWED_ORIGINS` is unset (default `*`)                 | Any origin can call the backend.                                | Acceptable for an MVP that does not store user secrets. **Recommended for prod:** set `CORS_ALLOWED_ORIGINS=https://<your-vercel-domain>` (comma-separated for multiple). The backend parses it via `core.cors.resolved_cors_origins`. |
| `/uploads/*` static mount writes to ephemeral container disk                      | Uploaded scan thumbnails are **lost** on every Railway redeploy. | **Phase 4 fix:** set `STORAGE_BACKEND=supabase` plus `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` / `SUPABASE_STORAGE_BUCKET=scan-images`. Scan images are then uploaded to the public Supabase Storage bucket and `scan_results.image_path` stores the object key (`scans/YYYY/MM/<uuid>_<file>`). Public URL is mirrored into `metadata_json.image_public_url` and surfaced through `/scans/history` as `image_url`. The backend falls back to the legacy `backend/uploads/` write whenever Storage is disabled or the upload errors out — `/predict` never breaks. |
| `.env` shipped to Railway is the **single** source of secrets                     | Anyone with Railway admin access reads `DATABASE_URL`.          | Use Railway role-based access; rotate Supabase password if a teammate leaves the project.        |

---

## 9. Rollback

### Backend (Railway)

1. Railway → **Deployments**.
2. Find the previous green deploy (`Deployed` status).
3. Click the "⋯" menu → **Rollback**. Traffic is shifted within ~30 s.

If a bad config change rather than bad code is at fault:

1. Railway → **Variables** → revert the offending value.
2. Service automatically restarts.

### Frontend (Vercel)

1. Vercel → **Deployments**.
2. Find the previous green deploy.
3. Click the "⋯" menu → **Promote to Production**. Atomic — no downtime.

### Database (Supabase)

* `0001_init.sql`, `0002_seed.sql`, `0003_audit_log.sql` are
  **idempotent**: re-running them is safe.
* Real data rollback: Supabase Dashboard → **Database → Backups** →
  PITR (paid tier) or daily snapshot (free tier).

### Total rollback (panic button)

1. Vercel: promote the last-known-good deploy (frontend stops calling
   anything new).
2. Railway: rollback to the last-known-good deploy.
3. Verify with the `/health/*` curls from [§5](#5-post-deploy-verification).

---

## Appendix A — Render alternative

If you ever want to move the backend to Render instead, drop the
following `render.yaml` at the repo root and import the repo in
Render's dashboard. Everything else (Vercel, Supabase, env vars) stays
the same.

```yaml
# render.yaml — Render alternative (not committed today; create it if you migrate).
services:
  - type: web
    name: plantvision-api
    runtime: python
    plan: starter
    rootDir: backend
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    healthCheckPath: /health
    autoDeploy: true
    envVars:
      - key: PERSISTENCE_BACKEND
        value: postgres
      - key: DATABASE_URL
        sync: false                       # paste in Render dashboard, never in YAML
      - key: PERSIST_EVENTS
        value: "true"
      - key: PERSIST_SENSOR_HISTORY
        value: "true"
      - key: PERSIST_SCAN_HISTORY
        value: "true"
      - key: YOLO_CONF
        value: "0.25"
      - key: YOLO_IMGSZ
        value: "640"
```

After updating `PLANT_API_BASE` on Vercel to the new Render URL and
redeploying the frontend, the cutover is complete.

---

## Appendix B — Related runbooks

* [`README.md`](README.md) — project overview and local quickstart.
* [`SETUP_PHASE2.md`](SETUP_PHASE2.md) — Supabase Cloud setup, schema
  migrations, manual verification checklist.
* [`PHASE3.md`](PHASE3.md) — reliability, audit log, retry telemetry,
  unified `/report` runbook.
* [`docs/setup_backend.md`](docs/setup_backend.md) — backend developer
  onboarding.
* [`docs/setup_frontend.md`](docs/setup_frontend.md) — frontend
  developer onboarding.
