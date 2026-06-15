# PlantVision — Phase Final · Graduation Submission

**Submission date:** July 1, 2026
**Tests:** 131 / 131 passing (`cd backend; python -m pytest -q`)
**Status:** demo-ready, end-to-end working, frontend Demo Mode as
fallback if the live backend or sensors are unavailable.

This document is the **single entry point** for the graduation jury.
For deep architectural detail, see [`README.md`](README.md),
[`PHASE3.md`](PHASE3.md), [`PHASE4.md`](PHASE4.md), and
[`DEPLOY.md`](DEPLOY.md). This file is the executive summary plus the
exact runbook for the demo.

---

## 1. Project overview

PlantVision is an end-to-end AI + IoT plant-monitoring system designed
around three real, live data flows: an ESP32 sensor node streams
environmental readings into Supabase, a vision model classifies plant
disease from a leaf photo, and a unified `/report` endpoint synthesises
those signals into a structured plant health report — a hero score, a
disease risk band, an environmental-stress band, a survival chance, a
sensor-aware care plan, and a list of warnings — without any LLM in the
critical path. The frontend is a vanilla HTML/CSS/JS mobile-first PWA
that consumes those endpoints and renders a hero health ring, sensor
KPI cards, a scan log with thumbnails from Supabase Storage, a
7-point Chart.js health-trend chart, a warnings strip, a care card, and
a Plant Profile / Garden / Analytics surface.

PlantVision was built layer-by-layer (Phases 1–4 + Final) so every layer
is independently runnable and independently testable. The backend
degrades gracefully — if Supabase is unreachable it falls back to
in-memory stores; if YOLO weights are missing it falls back to a
deterministic stub; if Pl@ntNet is not wired the stub returns Cucumber
so the rest of the pipeline keeps working. The frontend has a
**Demo Mode** toggle that short-circuits every backend call to canned
fixtures, so the dashboard still demos coherently when the WiFi, the
sensor, or the backend cold-start the moment the professor walks in.

---

## 2. Architecture

```mermaid
flowchart LR
    subgraph Edge
        ESP32[ESP32<br/>DHT22 · BH1750 · RS485]
        Cam[Camera / upload]
    end

    subgraph Frontend[Vercel — vanilla PWA]
        UI[Home · Garden · Plants · Analytics · Settings]
        Demo[Demo Mode<br/>canned fixtures + scenario toggle]
    end

    subgraph Backend[Railway — FastAPI · uvicorn]
        Predict[/POST /predict/]
        Sensor[/POST /sensor/]
        Report[/POST /report/]
        Care[/GET /care/{plant_id}/]
        Scans[/GET /scans/*/]
        Devices[/GET /devices/diagnostics/]
        Health[/GET /health/*/]
    end

    subgraph Services
        Vision[YOLO / stub]
        PlantId[stub · Pl@ntNet wrapper]
        CareEng[care_engine]
        ReportB[report_builder]
        Retry[core.retry + audit_log]
    end

    subgraph Supabase[Supabase Cloud]
        DB[(scan_results · sensor_readings · zones · devices · audit_log · analytics_events)]
        Storage[(Storage bucket<br/>scan-images)]
    end

    ESP32 -- POST /sensor --> Sensor --> DB
    Cam --> UI -- POST /predict --> Predict --> Vision
    Predict --> PlantId
    Predict --> Storage
    Predict --> DB
    UI -- POST /report --> Report --> ReportB
    Report --> Vision
    Report --> PlantId
    Report --> CareEng
    UI -- GET /scans/* / /care / /devices / /health --> Backend
    Backend --> Retry --> DB
    UI -. when backend down .-> Demo
```

---

## 3. Features that ship

### Backend (FastAPI)
- `POST /predict` — image upload, validates the JPEG, runs YOLO (or
  stub), runs plant identification (stub or Pl@ntNet wrapper), uploads
  the image to Supabase Storage (with local fallback), persists a
  `scan_results` row, returns a `VisionResult` envelope.
- `POST /sensor` — validates a strict Pydantic `SensorReading`, persists
  with bounded retry + audit-log telemetry, caches the latest reading
  per device.
- `POST /report` — unified Phase 3 envelope: vision + plant ID + sensor +
  care plan + scores + warnings + analysis summary.
- `GET /sensor/latest` — live or DB-hydrated, marks freshness.
- `GET /scans/history`, `/scans/zone-counts`, `/scans/plant/{id}`,
  `/scans/{id}` — DB-backed with memory fallback, includes `image_url`
  resolved from Supabase Storage public URLs.
- `GET /care/{plant_id}` — care template + sensor-aware diff.
- `GET /devices/diagnostics` · `POST /devices/register` — ESP32 device
  registry + freshness counters.
- `GET /zones` — zone management for multi-tenant defaults.
- `GET /health`, `/health/db`, `/health/sensor`, `/health/audit` —
  liveness, Supabase reachability, per-device freshness + retry
  telemetry, audit-log tail.

### Data (Supabase Cloud · Postgres)
- Tables: `scan_results`, `sensor_readings`, `zones`, `devices`,
  `audit_log`, `analytics_events`.
- Migrations: `0001_init.sql` (core schema), `0002_seed.sql` (demo
  fixtures), `0003_audit_log.sql`, `0004_multitenant_indexes.sql`.
- `scan-images` Supabase Storage bucket for persistent scan thumbnails
  across Railway redeploys.

### AI / ML
- YOLOv8 disease detection (real weights when present, deterministic
  stub fallback).
- `StubPlantIdPredictor` (default — locks to Cucumber) and
  `PlantNetPredictor` (Pl@ntNet v2 wrapper that transparently falls
  back to the stub on missing key / network / 4xx / 5xx / malformed
  response).
- `plant_health` scoring: hero score, disease risk, environment stress,
  survival chance.
- `care_engine`: 6-species YAML templates diffed against live sensor
  readings.
- `report_builder`: assembles the unified `/report` envelope.

### Frontend (vanilla HTML/CSS/JS PWA · Vercel)
- Home dashboard: hero plant-health ring, sensor KPI cards (temp,
  humidity, soil moisture, lux), warnings strip, care card, latest-scan
  card with thumbnail, **health-trend Chart.js chart** (last 7 scans),
  scan log with 3 most-recent entries + thumbnails from Supabase
  Storage.
- Plants / Garden / Analytics / Settings tabs.
- Scan modal → result modal flow with disease label, confidence, health
  block, and care recommendation.
- **Demo Mode** with healthy / warning scenario toggle, DEMO chip in
  topbar, ISO timestamps recomputed on every read, SVG data-URI leaf
  thumbnails so demo scans never reference broken URLs.
- **Offline banner**: pops up at the top of the content area when the
  backend health probe fails OR when the browser fires `offline`. Tells
  the user how to enable Demo Mode. Auto-hides when Demo Mode is on or
  the backend recovers.
- **Loading skeletons**: pulsing shimmer on dashboard stat cards while
  the initial fetch is in flight.
- **Empty states**: dedicated empty messages on the Home scan log,
  Garden devices list, and Scan history filters.
- Mobile-first responsive at 360px / 768px / 1024px. Theme tokens
  (`--sage`, `--gold`, `--coral`) preserved exactly as shipped.

### Ops
- GitHub Actions CI runs `python -m pytest -q` on every push.
- `backend/Procfile` + `backend/railway.toml` bind `0.0.0.0:$PORT` and
  health-check `/health`.
- `frontend/vercel.json` sets `outputDirectory: mobile-app` and rewrites
  `env.js` at deploy time to embed `PLANT_API_BASE`.
- `.env.example` documents every `os.getenv` reference.
- `.gitignore` blocks real `.env`, `*.pt`, `backend/uploads/`, and
  binary dataset artifacts.
- `DEPLOY.md` has a pre-submission checklist and a "if the live demo
  fails" Demo Mode fallback section.

---

## 4. Final demo flow (end-to-end live)

The professor will see this exact sequence:

1. **Edge — sensor publishes.** ESP32 fires `POST /sensor` every ~10s
   with a fresh `SensorReading` (temp, humidity, soil moisture, light,
   pH, EC).
2. **Backend — validate + persist.** FastAPI validates against
   `schemas.sensors.SensorReading`, persists to Supabase
   `sensor_readings` with bounded retry, caches the latest reading in
   memory keyed by `(user, zone, device)`, and emits an audit-log entry
   on failure.
3. **Frontend polls — Home dashboard updates.** Every 6 seconds the Home
   page calls `GET /sensor/latest`, `POST /report`, and
   `GET /scans/history?limit=7`. Sensor KPI cards refresh, the **hero
   plant-health ring** tones at thresholds 75 / 50, the **warnings**
   strip surfaces any active warnings, the **care card** shows the most
   recent care plan, and the **Chart.js trend** chart redraws.
4. **Edge — operator snaps a leaf.** They click the scan button in the
   Home page → choose Camera or Upload → confirm.
5. **Backend — vision pipeline runs.** `POST /predict` validates the
   image, runs YOLO (or the stub), runs `PlantIdPredictor` (stub →
   Cucumber, or PlantNet wrapper → real species when wired), uploads
   the image to Supabase Storage `scan-images` bucket under
   `scans/YYYY/MM/<uuid>_<filename>`, persists a row in `scan_results`
   with the image path + metadata, returns a `VisionResult` envelope.
6. **Frontend — result modal populates.** The modal shows disease,
   confidence, health block, plant identification, and the next
   recommended care action.
7. **Frontend — Home dashboard refreshes.** Latest-scan card, scan log,
   hero ring, warnings strip, and trend chart all roll forward with the
   new datapoint.
8. **Backend — analytics + audit.** The scan is counted in
   `analytics_events`; any retry / validation failure is appended to
   `audit_log`.
9. **Operator opens Garden / Plants / Analytics tabs.** Same data,
   different surfaces — Garden shows per-device cards, Plants shows a
   filterable profile, Analytics shows totals + pass-rate + insights.
10. **Operator enables Demo Mode (optional).** Settings → Demo Mode →
    toggle ON. The DEMO chip lights up amber in the topbar and every
    fetch is replaced with a canned fixture, so the same dashboard
    works even without the backend.

---

## 5. Setup (clean clone → running demo)

```powershell
# 1. Clone the repo
git clone <your-repo-url> plant-ai-project
cd plant-ai-project

# 2. Configure environment
copy .env.example .env
# Edit .env with your DATABASE_URL (Supabase Transaction Pooler URI),
# SUPABASE_URL, SUPABASE_SERVICE_KEY, SUPABASE_STORAGE_BUCKET=scan-images.

# 3. Install backend dependencies
pip install -r backend/requirements.txt

# 4. (Optional) Apply Phase 3+4 Supabase migrations
python scripts/apply_migration_0003.py
# Then in the Supabase SQL editor run supabase/migrations/0004_multitenant_indexes.sql.

# 5. Run the backend
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# 6. In a second terminal, run the frontend static server
cd frontend\mobile-app
node server.js

# 7. Open
# Frontend → http://localhost:3000
# FastAPI  → http://localhost:8000/docs
```

For full deploy instructions (Railway + Vercel), see
[`DEPLOY.md`](DEPLOY.md).

---

## 6. Testing

### Automated

```powershell
cd backend
python -m pytest -q
# expected: 131 passed in <2s
```

The suite forces `PERSISTENCE_BACKEND=memory` at conftest level, so it
never reaches Supabase, never reaches the network, and is fully
self-contained.

### Manual test checklist

Run this list once during the dry-run and once again 2 hours before the
demo. Each step takes < 30 seconds; the whole list is ≈ 3 minutes.

1. Start the backend:
   `cd backend; python -m uvicorn main:app --reload --port 8000`.
2. `curl http://localhost:8000/health/db` → expect
   `status: "supabase_cloud_connected"` (or
   `status: "memory_fallback"` if running locally without DB).
3. `curl http://localhost:8000/health/sensor` → expect per-device
   freshness JSON with `status` in `{healthy, degraded, offline}` and
   retry counters.
4. `curl -F "file=@<path-to-leaf.jpg>" http://localhost:8000/predict` →
   expect a `VisionResult` with `disease`, `confidence`, `health`
   block, and (when `STORAGE_BACKEND=supabase`)
   `metadata.image_public_url`.
5. Open Supabase Dashboard → Storage → `scan-images` → confirm a new
   file exists with path `scans/YYYY/MM/<uuid>_<filename>`.
6. `curl "http://localhost:8000/scans/history?limit=1"` → confirm the
   latest item's `image_url` is the Supabase public URL.
7. Open the frontend, click the Home scan button, complete a scan; the
   result modal must populate with disease + confidence + health.
8. Confirm the Home dashboard updates: hero health ring tones with the
   new score, warnings strip surfaces any active warning, care card
   shows the latest care plan, latest-scan thumbnail renders.
9. Toggle Demo Mode in Settings → confirm the DEMO chip lights up amber
   in the topbar and the dashboard populates with fixture data
   (sensor, scans, trend chart).
10. Resize the browser to 360px width → confirm the mobile layout does
    not break: scan button reachable, cards stack vertically, trend
    chart resizes.

---

## 7. Known limitations

Honest list — read this before the jury Q&A so you are not caught off
guard.

- **Plant identification is an MVP stub.** Default `PLANT_ID_MODEL=stub`
  returns Cucumber / *Cucumis sativus* / Cucurbitaceae for every leaf.
  A real Pl@ntNet integration is wired and tested (see
  `backend/models/plant_id_model.py::PlantNetPredictor` and the 4 unit
  tests in `backend/tests/test_plant_id.py`), but is only active when
  the operator sets `PLANT_ID_MODEL=plantnet` and provides a
  `PLANT_ID_API_KEY`. Without those, the wrapper falls back to the stub
  transparently. We chose to keep stub as the demo default so the
  pipeline never depends on Pl@ntNet's free-tier latency or
  availability on demo day.
- **Local `backend/uploads/` is ephemeral on Railway.**
  `STORAGE_BACKEND=supabase` (already wired in
  `services/storage.py`) is required for scan images to persist across
  Railway redeploys.
- **The `scan-images` Supabase Storage bucket is public** for demo
  simplicity, not private with signed URLs. Future hardening would
  rotate the bucket to private and serve via short-lived signed URLs.
- **Authentication is not required** for the demo. Everything runs
  under the synthetic `demo_user`. There is no login screen, no JWT,
  no Supabase Auth wiring.
- **Multi-tenant support exists in the database** (`user_slug` on
  `sensor_readings`, indexes in
  `supabase/migrations/0004_multitenant_indexes.sql`) but the frontend
  always uses the `demo_user` / `zone_alpha` / `esp32_001` defaults.
  Switching tenants is a 1-day follow-up.
- **No real-time push.** The frontend polls every 6 seconds for sensor
  + report data. Supabase Realtime / WebSockets is a Phase 5+ item.
- **No mobile native app.** Frontend is a responsive PWA — installable
  to the home screen but not packaged as iOS / Android binaries.
- **Some startup-grade features are documented in `PHASE4.md` /
  strategy notes but intentionally not implemented for the graduation
  submission**: AR overlays, voice assistant, closed-loop irrigation,
  yield prediction, outbreak alerts, sensor-fusion heatmaps,
  Stripe/billing, GDPR workflows. These are explicitly **out of scope**
  for this submission.

---

## 8. Future work

Once the graduation submission is in, the roadmap (already drafted in
`PHASE4.md` and the strategy notes from the earlier reviews) is:

- **Phase 5 — Realtime + Auth.** Wire Supabase Realtime channels into
  the Home dashboard so sensor updates push instead of poll. Add
  Supabase Auth (email magic-link) so each operator sees only their own
  zones.
- **Phase 6 — Closed-loop control.** ESP32 firmware update so warnings
  emitted by `/report` can trigger a relay (pump on / fan on / shade
  net deploy). Audit-log every actuation.
- **Phase 7 — Yield prediction + outbreak alerts.** Persistent feature
  store, time-series model for yield, anomaly detection across a fleet
  of plants for outbreak flagging.
- **Hardening.** Rotate the `scan-images` bucket to private + signed
  URLs, swap synthetic `demo_user` for real Supabase Auth, finalize the
  multi-tenant frontend.

---

## 9. Screenshots checklist

Before submitting, capture screenshots of the following — both with
Demo Mode ON (clean story) and OFF (live story). Save as PNG at the
default browser resolution.

- [ ] Home — full dashboard (hero ring + warnings + care card + sensor
      KPIs + latest scan + trend chart + scan log).
- [ ] Home — same view at 360px width (mobile layout).
- [ ] Scan source modal (Camera / Upload picker).
- [ ] Scan result modal (with disease, confidence, health block, care
      action).
- [ ] Garden — per-device cards with freshness chips.
- [ ] Plants / Profile — plant detail with care plan + scan history.
- [ ] Analytics — totals, pass-rate, insights.
- [ ] Settings — Demo Mode card with DEMO chip visible in topbar.
- [ ] Settings — Devices diagnostics table.
- [ ] Topbar — `AI Ready` + `System Online` chips green (live path).
- [ ] Topbar — `DEMO` chip lit amber (demo path).
- [ ] Supabase Dashboard → Storage → `scan-images` showing real
      uploaded files (proof of the persistent storage layer).
- [ ] Supabase Dashboard → Table editor → `scan_results` with rows.

---

## 10. What to show the professor (60-second demo script)

> Speak the bracketed lines aloud, click the bold actions.

1. **Open the live frontend URL.**
   "PlantVision is an end-to-end AI + IoT plant-monitoring system. The
   ESP32 streams sensor data into Supabase, FastAPI synthesises a
   plant report, and the frontend renders it."
2. **Point at the topbar chips.**
   "AI Ready, System Online — the backend is reachable and Supabase is
   responding."
3. **Point at the hero plant-health ring + warnings + care card.**
   "This hero ring is computed from real sensor data plus the latest
   scan. The warnings strip and care card are reactive — the moment a
   sensor goes out of range, the care card tells the operator what to
   do."
4. **Point at the trend chart.**
   "Last 7 scans on a Chart.js line chart, tones with the latest
   health score."
5. **Click Scan → Upload → pick a leaf image → confirm.**
   "The vision model classifies the leaf, the image is uploaded to
   Supabase Storage, and a new row lands in `scan_results`."
6. **Show the populated result modal.**
   "Disease, confidence, plant ID, health block, care action — all in
   one round-trip to `/predict`."
7. **Dismiss the modal → point at the updated scan log + trend chart.**
   "The Home dashboard rolled forward with the new datapoint."
8. **Open Settings → Demo Mode → toggle ON.**
   "If the conference WiFi or the backend dies mid-demo, we fall back
   to a frontend-only Demo Mode. The DEMO chip in the topbar is the
   signal."
9. **Navigate back to Home.**
   "Same dashboard, fixture data, no backend required. The
   presentation never breaks."
10. **Toggle Demo Mode OFF, end the demo on the live data view.**

---

## 11. What NOT to show the professor

- Do not scan a non-cucumber leaf and let the screen sit on
  "Cucumber / Cucumis sativus" — that's the stub Plant ID returning
  Cucumber for every plant. Either accept it as the documented MVP
  limitation, or switch `PLANT_ID_MODEL=plantnet` + provide a real
  Pl@ntNet API key before the demo.
- Do not open the Supabase dashboard and show the
  `scan-images` bucket policy — it is currently **public** for demo
  simplicity, which is documented as a known limitation but not a great
  look on stage.
- Do not click anything that exposes the hard-coded `demo_user` /
  `zone_alpha` / `esp32_001` defaults (e.g. raw `GET /sensor/latest`
  query strings). The multi-tenant schema is in place; the frontend
  has not yet been switched off the default tenant. Frame it as Phase 5
  if asked.
