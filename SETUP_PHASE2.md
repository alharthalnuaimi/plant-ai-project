# PlantVision — Phase 2 Local Persistence Setup

This document walks through running PlantVision with a local
Supabase-compatible Postgres instance. The frontend continues to work
exactly as before when the database is offline; persistence is purely
additive.

---

## 1. Prerequisites

| Tool            | Tested version | Notes                                       |
| --------------- | -------------- | ------------------------------------------- |
| Docker Desktop  | 24+            | Used to run Postgres / Supabase Studio      |
| Python          | 3.11+          | FastAPI backend                             |
| Node.js         | 18+            | Static frontend dev server                  |

---

## 2. Quick start (TL;DR)

```bash
# 1. Bootstrap env file
cp .env.example .env

# 2. Start the database stack (Postgres + Studio + meta)
docker compose up -d

# 3. Install backend deps (asyncpg is the only new one)
cd backend
pip install -r requirements.txt

# 4. Run FastAPI
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 5. In another terminal — run the frontend dev server
cd ../frontend/mobile-app
node server.js
```

Open:

* Frontend          → http://localhost:3000
* FastAPI docs      → http://localhost:8000/docs
* Supabase Studio   → http://localhost:54324
* Postgres direct   → `psql postgresql://postgres:plantvision_dev@localhost:54322/plantvision`

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                       Frontend (vanilla JS)                  │
│   home.js | garden.js | assistant.js | settings.js | app.js  │
│                            │                                 │
│                          api.js                              │
└────────────┬────────────────┬────────────────────────────────┘
             │                │
             ▼                ▼
        FastAPI (backend/main.py)
          │
          │  routes/ ── REST API (predict, sensor, zones, devices…)
          │     │
          │     ▼
          │  services/ ── business logic + in-memory caches
          │     │
          │     ▼
          │  repositories/ ── ONLY layer that talks SQL
          │     │
          │     ▼
          │  db/connection.py ── asyncpg pool (lazy, optional)
          ▼
     ┌──────────────────────────────────────┐
     │       Postgres (supabase/postgres)   │
     │       via Docker, port 54322         │
     └──────────────────────────────────────┘
```

Key rule: **routes never see SQL**. They call services, services call
repositories, repositories own the SQL. This makes it trivial to swap
asyncpg for `supabase-py` later, or to add caching, retries, or
read-replicas without touching the API surface.

When `PERSISTENCE_BACKEND=memory` (or the DB is unreachable), every
repository call is a graceful no-op that returns `[]` / `None`. The
in-memory MVP stores keep serving reads so the UI never breaks.

---

## 4. Database schema

Migrations live in `supabase/migrations/` and are applied automatically
by Postgres on first boot (mounted into `/docker-entrypoint-initdb.d`).

| Table              | Purpose                                          |
| ------------------ | ------------------------------------------------ |
| `zones`            | Growing zones (Alpha, Beta, …) with geo + status |
| `devices`          | ESP32 sensor nodes attached to a zone            |
| `sensor_readings`  | Time-series sensor stream                        |
| `scan_results`     | YOLO + plant-health enriched scan output         |
| `analytics_events` | Activity feed (scans, alerts, sensor pulses)    |
| `assistant_logs`   | Optional Q/A history (rule-based assistant)      |

Schema details: see [`supabase/migrations/0001_init.sql`](supabase/migrations/0001_init.sql).

To re-apply migrations after editing:

```bash
docker compose down -v   # drops the volume
docker compose up -d
```

---

## 5. Environment variables

Copy `.env.example` → `.env` and adjust as needed. The most important
toggles:

| Variable                     | Default                                                | What it does                                          |
| ---------------------------- | ------------------------------------------------------ | ----------------------------------------------------- |
| `PERSISTENCE_BACKEND`        | `memory` in `.env.example`, set to `postgres` to persist | Master switch. `memory` keeps legacy MVP behaviour. |
| `DATABASE_URL`               | Derived from POSTGRES_*                                | asyncpg connection DSN                                |
| `POSTGRES_HOST/PORT/USER/DB` | `localhost:54322`                                      | Used to build DATABASE_URL if you don't override     |
| `PERSIST_EVENTS`             | `true`                                                 | Save `_push_event` calls to `analytics_events`        |
| `PERSIST_SENSOR_HISTORY`     | `true`                                                 | Save each `/sensor` payload to `sensor_readings`      |
| `PERSIST_SCAN_HISTORY`       | `true`                                                 | Save each `/predict` result to `scan_results`         |

`.env` is git-ignored; `.env.example` is committed.

---

## 6. Files added / changed

### Backend (added)

* `backend/config/settings.py` — env-driven settings loader (.env aware)
* `backend/db/__init__.py`
* `backend/db/connection.py` — asyncpg pool with graceful fallback
* `backend/repositories/__init__.py`
* `backend/repositories/zones_repo.py`
* `backend/repositories/devices_repo.py`
* `backend/repositories/sensor_repo.py`
* `backend/repositories/scans_repo.py`
* `backend/repositories/analytics_events_repo.py`
* `backend/repositories/assistant_repo.py`
* `backend/services/persistence.py` — best-effort fire-and-forget writes
* `backend/services/garden_management.py` — zones/devices hybrid store
* `backend/schemas/garden_management.py` — Pydantic models
* `backend/routes/zones.py` — CRUD `/zones`
* `backend/routes/devices.py` — CRUD `/devices`

### Backend (changed)

* `backend/main.py` — register new routers, startup/shutdown hooks,
  `GET /health/db`
* `backend/config/__init__.py` — export SETTINGS
* `backend/services/analytics_store.py` — emit best-effort persistence
  calls when scans / sensor readings / events are recorded
* `backend/requirements.txt` — add `asyncpg`

### Frontend (added)

* API helpers in `frontend/mobile-app/api.js`:
  * `fetchZones`, `saveZone`, `deleteZone`
  * `fetchDevices`, `saveDevice`, `deleteDevice`
  * `fetchDbHealth`

### Frontend (changed)

* `frontend/mobile-app/app.js`
  * `saveZones()` now mirrors writes to FastAPI in parallel with the
    existing Node sync.
  * New `hydrateZonesFromBackend()` runs on app boot and prefers the
    persisted server state when `source === "postgres"`.
  * Sidebar mini chip reflects DB reachability.

### Infrastructure (added)

* `docker-compose.yml` (repo root) — Postgres + meta + Studio
* `supabase/migrations/0001_init.sql` — schema
* `supabase/migrations/0002_seed.sql` — default zones / device
* `.env.example` — env template (`.env` ignored by Git)

---

## 7. Commands cheat-sheet

```bash
# Stack
docker compose up -d            # Start DB / Studio / meta
docker compose ps               # Status
docker compose logs -f postgres # Tail Postgres logs
docker compose down             # Stop (keeps data)
docker compose down -v          # Stop + DROP all data (re-runs migrations)

# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend
cd frontend/mobile-app
node server.js

# Smoke
curl http://localhost:8000/health
curl http://localhost:8000/health/db
curl http://localhost:8000/zones
```

---

## 8. Testing checklist

### Backend

* [ ] `docker compose up -d` brings Postgres up healthy (`docker compose ps`)
* [ ] `GET /health` returns `{"status": "ok"}`
* [ ] `GET /health/db` returns `persistence_backend: "postgres"` and
  `postgres_reachable: true`
* [ ] `GET /zones` returns the 3 seeded zones (`source: "postgres"`)
* [ ] `POST /zones` upserts a new zone; visible in Supabase Studio
* [ ] `POST /devices` upserts a device tied to a zone
* [ ] `POST /sensor` (ESP32 payload) returns a reading AND inserts into
  `sensor_readings`
* [ ] `POST /predict` (image upload) returns a `VisionResult` AND
  inserts into `scan_results`
* [ ] Stopping Docker mid-session does not crash the API — repositories
  log a warning and the in-memory store keeps serving

### Frontend

* [ ] Sidebar shows `DB` mini chip with green dot when DB is reachable
* [ ] After adding a zone in the UI, restarting the frontend still
  shows it (now coming from Postgres, not localStorage)
* [ ] Stopping Docker → sidebar mini chip turns amber `DB` → app still
  works, falling back to local state
* [ ] Simulation mode (Settings → Sensors) still functions exactly as
  before
* [ ] Camera scan, image-upload scan, scan-result modal, chatbot
  context, Home live state, Analytics, Garden, Profile all behave as
  before
* [ ] AI Assistant quick-action chips (Plant Health / Latest Scan /
  Zone Status / Sensor Summary / What Should I Do?) return formatted
  rich cards

### ESP32

* [ ] Sending a POST to `/sensor` from the ESP32 (or
  `curl -X POST` with the same JSON body) appends a row to
  `sensor_readings` and bumps `devices.last_seen`

---

## 9. Known limitations

* No authentication / RLS — local dev only. **Do not expose port 54322
  on the public internet.**
* No migrations runner beyond the Postgres init-volume. To re-run
  migrations you drop the volume (`docker compose down -v`). A future
  iteration can add Alembic or `supabase migration up`.
* Sensor history table can grow unbounded — add a retention policy
  (pg_cron / partitioning) when scaling beyond local dev.
* Frontend zone status enum (`Healthy` / `At Risk` / `Critical` /
  `Offline`) is translated to/from backend `HEALTHY` / `WARNING` /
  `CRITICAL` / `OFFLINE` in `app.js`. If you add new statuses, update
  both maps.
* The `/predict` endpoint still saves the uploaded image to
  `backend/uploads/`; only the metadata is persisted to Postgres.
  Object storage (Supabase Storage / S3) is a future step.
* Replacing asyncpg with `supabase-py` is a drop-in repository
  refactor — the rest of the codebase doesn't need to change.

---

## 10. Switching to the full Supabase CLI later

If you prefer the full Supabase local stack (auth, realtime, storage,
edge functions), you can switch to the Supabase CLI without rewriting
anything:

```bash
npx supabase init
npx supabase start
# Re-point DATABASE_URL to the CLI's port (default 54322 — same as ours)
```

Our migrations under `supabase/migrations/` are CLI-compatible, so
`supabase db reset` will pick them up automatically.
