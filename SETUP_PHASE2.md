# PlantVision — Phase 2 Persistence Setup (Supabase Cloud)

This is the recommended Phase 2 path for the PlantVision team. It uses
**Supabase Cloud (managed Postgres)** as the persistence backend — no
Docker, no WSL, no BIOS virtualization required on teammates' PCs.

Phase 1 functionality (sensor POST, scan pipeline, analytics, garden
command center, AI assistant, UI polish) is unchanged. If the DB is
unreachable, the backend automatically falls back to the in-memory store
and the app keeps working.

> Architecture stays the same:
> **Frontend → FastAPI → Supabase Postgres** (no direct frontend → Supabase calls).

---

## 1. Prerequisites

| Tool     | Tested version | Notes                                 |
| -------- | -------------- | ------------------------------------- |
| Python   | 3.11+          | FastAPI backend                       |
| Node.js  | 18+            | Static frontend dev server            |
| Supabase | Free tier      | Cloud project — no install needed     |
| Docker   | _(optional)_   | Only for the optional local Postgres  |

---

## 2. Set up Supabase Cloud (one-time, ~5 minutes)

### a. Create a Supabase project

1. Sign in at [https://supabase.com](https://supabase.com) (GitHub login works).
2. Click **New project**.
3. Name it `plantvision` (or anything you like), pick a region close to
   you, and choose a strong database password. **Save the password** —
   you'll need it once and Supabase can't show it again.
4. Wait ~1 minute for the project to provision.

### b. Open the SQL Editor and run the schema migration

1. In the left sidebar of your Supabase project, open **SQL Editor**.
2. Click **+ New query**.
3. Open the local file [`supabase/migrations/0001_init.sql`](supabase/migrations/0001_init.sql),
   copy its full contents, paste into the SQL editor, and press **Run**.
4. You should see "Success. No rows returned."

### c. Run the seed migration

1. Open a new SQL query.
2. Paste the contents of [`supabase/migrations/0002_seed.sql`](supabase/migrations/0002_seed.sql)
   and press **Run**.
3. Verify the seed: under **Table Editor → `zones`** you should see three
   rows (`zone_alpha`, `zone_beta`, `zone_gamma`); under `devices` you
   should see `esp32_001`.

### d. Copy the Postgres connection string

1. Open **Settings → Database → Connection string**.
2. Choose the **URI** tab and the **Transaction pooler** mode (port `6543`).
3. Copy the string. It looks like:

   ```text
   postgresql://postgres.PROJECT_REF:[YOUR-PASSWORD]@aws-0-REGION.pooler.supabase.com:6543/postgres
   ```

4. Replace `[YOUR-PASSWORD]` with the password you set in step (a).
   If your password contains special characters (`@`, `/`, `:`, `#`,
   `%`, `?`, etc.), URL-encode them.

> **Why the transaction pooler (6543)?** FastAPI / asyncpg open many
> short-lived connections per request; the pooler is what Supabase
> recommends for this workload. The direct connection on port `5432`
> also works but is rate-limited on the free tier.

### e. Put it in `.env` only (never commit it)

```bash
cp .env.example .env
```

Then edit `.env` and replace the placeholder `DATABASE_URL` line with
your real connection string. `.env` is git-ignored — don't paste real
passwords anywhere else.

---

## 3. Run the backend in postgres mode

```powershell
# From repo root
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Watch the startup log. With `PERSISTENCE_BACKEND=postgres` and a valid
Supabase `DATABASE_URL` you should see:

```text
INFO plantvision.db Postgres pool ready [cloud] host=aws-0-...pooler.supabase.com db=postgres ssl=on
```

If you instead see:

```text
WARNING plantvision.db Postgres unavailable (...); falling back to memory store.
```

…then check your `DATABASE_URL`, password, and that the project is in
the "Healthy" state on the Supabase dashboard. The API will still
respond — it just won't persist.

In another terminal:

```powershell
cd frontend\mobile-app
node server.js
```

Open:

* Frontend     → [http://localhost:3000](http://localhost:3000)
* FastAPI docs → [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 4. Verify persistence end-to-end

### a. Check `/health/db`

```powershell
curl http://localhost:8000/health/db
```

Expected (Cloud connected):

```json
{
  "persistence_backend": "postgres",
  "deployment": "cloud",
  "status": "supabase_cloud_connected",
  "postgres_reachable": true,
  "database_host": "aws-0-REGION.pooler.supabase.com",
  "database_port": 6543,
  "database_name": "postgres"
}
```

If the DB is unreachable you'll get `status: "postgres_unreachable"`
and the backend keeps serving with the memory fallback.

### b. POST a sensor reading

```powershell
curl -X POST http://localhost:8000/sensor `
  -H "Content-Type: application/json" `
  -d '{
        "user_id": "demo_user",
        "zone_id": "zone_alpha",
        "device_id": "esp32_001",
        "air_temperature": 25.2,
        "air_humidity": 73,
        "light_lux": 780,
        "soil_temperature": 28.2,
        "soil_humidity": 46,
        "soil_ph": 6.1,
        "soil_ec": 1.6
      }'
```

Then in Supabase Studio → **Table Editor → `sensor_readings`** you
should see one new row (refresh the table). The `analytics_events`
table should also have a "sensor updated" entry.

### c. Confirm persistence after a backend restart

This is the critical test that proves Supabase is the source of truth:

1. Stop the FastAPI process (`Ctrl+C`).
2. Start it again with the same command.
3. Without sending any new POST, hit:

   ```powershell
   curl http://localhost:8000/sensor/latest
   ```

   You should still get the values you just posted, with a non-zero
   `age_seconds`. This proves the data came from Supabase, not from
   in-process memory.

### d. Verify scan persistence (optional)

```powershell
curl -X POST http://localhost:8000/predict `
  -F "file=@some_leaf.jpg" `
  -F "user_id=demo_user" `
  -F "zone_id=zone_alpha"
```

Then in Supabase Studio → `scan_results` you should see one new row
with the prediction class, confidence, and health score.

### e. Verify zones / devices are readable

```powershell
curl http://localhost:8000/zones
curl http://localhost:8000/devices
```

`source` should be `"postgres"` when the DB is reachable.

---

## 5. Manual testing checklist

### Backend

* [ ] `GET /health` → `{"status":"ok"}`
* [ ] `GET /health/db` → `status: "supabase_cloud_connected"`
* [ ] `POST /sensor` → 200 + row in `sensor_readings`
* [ ] `GET /sensor/latest` returns the posted values
* [ ] **Restart backend** → `GET /sensor/latest` still returns the values
      (proves the read fell back to Supabase, not memory)
* [ ] `POST /predict` → 200 + row in `scan_results`
* [ ] `GET /zones` → 3 seeded rows, `source: "postgres"`
* [ ] Disconnect the network for 30s → API stays up, `/health/db` flips
      to `postgres_unreachable`, app keeps working in memory mode

### Frontend

* [ ] Home / Garden / Profile / Analytics / Assistant unchanged from Phase 1
* [ ] Sidebar mini DB chip turns green when `/health/db` is healthy
* [ ] Adding a zone in the UI is still visible after a frontend reload
      (data round-trips through Supabase via FastAPI, not localStorage)
* [ ] Simulation mode still functions when `PERSISTENCE_BACKEND=memory`

---

## 6. Architecture (unchanged from Phase 2 foundation)

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
          │  db/connection.py ── asyncpg pool (lazy, optional, TLS auto)
          ▼
     ┌─────────────────────────────────────────────┐
     │   Supabase Cloud  (managed Postgres + TLS)  │
     │   …or optional local Postgres on port 54322 │
     └─────────────────────────────────────────────┘
```

The frontend never talks to Supabase directly. The browser only talks
to FastAPI. This keeps the service-role key and DB credentials inside
the backend.

---

## 7. Configuration reference

`.env` is git-ignored; `.env.example` is committed with safe placeholders.

| Variable                  | Default               | Purpose                                                  |
| ------------------------- | --------------------- | -------------------------------------------------------- |
| `PERSISTENCE_BACKEND`     | `postgres`            | `postgres` = Supabase / local PG · `memory` = fallback   |
| `DATABASE_URL`            | _(placeholder)_       | Supabase Cloud pooler URI — required for `postgres` mode |
| `API_HOST`                | `0.0.0.0`             | uvicorn bind host                                        |
| `API_PORT`                | `8000`                | uvicorn bind port                                        |
| `YOLO_WEIGHTS_PATH`       | `artifacts/models/cucumber_yolov8.pt` | YOLO weights file (ignored by git)       |
| `PERSIST_EVENTS`          | `true`                | Write `analytics_events` rows                            |
| `PERSIST_SENSOR_HISTORY`  | `true`                | Write `sensor_readings` rows on each POST                |
| `PERSIST_SCAN_HISTORY`    | `true`                | Write `scan_results` rows on each prediction             |

TLS is auto-enabled when `DATABASE_URL` host ends with `.supabase.co` /
`.supabase.com`, so you don't need to add `?sslmode=require`.

---

## 8. Database schema (unchanged)

Migrations live in `supabase/migrations/`:

| Table              | Purpose                                          |
| ------------------ | ------------------------------------------------ |
| `zones`            | Growing zones (Alpha, Beta, …) with geo + status |
| `devices`          | ESP32 sensor nodes attached to a zone            |
| `sensor_readings`  | Time-series sensor stream                        |
| `scan_results`     | YOLO + plant-health enriched scan output         |
| `analytics_events` | Activity feed (scans, alerts, sensor pulses)    |
| `assistant_logs`   | Optional Q/A history                             |

Re-running `0001_init.sql` is safe (every statement is `if not exists`
or `on conflict do nothing`).

---

## 9. Optional — run Postgres locally with Docker

You almost certainly don't need this. Supabase Cloud is faster, easier,
and shared across the team. Keep this for offline dev or CI:

```powershell
# Start the local stack (Postgres on 54322 + Supabase Studio on 54324)
docker compose up -d

# Point the backend at it:
#   PERSISTENCE_BACKEND=postgres
#   DATABASE_URL=postgresql://postgres:plantvision_dev@localhost:54322/plantvision
```

Migrations are auto-applied on first boot (mounted into
`/docker-entrypoint-initdb.d`). Run `docker compose down -v` to wipe
the DB and re-apply migrations cleanly.

Local Docker is **not** required to use Phase 2. Anyone on the team
who can sign in to Supabase Cloud is fully set up.

---

## 10. Safety

* `.env` is git-ignored. Never commit real Supabase passwords or
  service-role keys.
* The frontend never calls Supabase directly; all DB access goes
  through FastAPI.
* If you accidentally pushed credentials, rotate the database password
  in **Supabase → Settings → Database → Reset password** and update
  every teammate's local `.env`.
* The memory fallback is permanent: even if Supabase is down, the
  backend boots cleanly and the demo keeps working.
