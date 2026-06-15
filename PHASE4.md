# PlantVision — Phase 4 runbook

Phase 4 is a polish + deployment-readiness pass over the working
Phase 3 MVP. It is intentionally split into two batches that ship
independently:

* **Batches A + B (this PR)** — safe, low-to-medium-risk, additive
  work. Production CORS allowlist, CI/CD, frontend Demo Mode,
  dashboard polish, ESP32 device health surface, Plant-ID decision
  matrix (this document), and a multi-tenant schema audit.
* **Batches C + D (deferred — require user sign-off)** — Supabase
  Storage for scan images, real Plant ID API integration, Supabase
  Auth, and full multi-tenant rollout. See the
  [§ What's still gated on sign-off](#whats-still-gated-on-sign-off)
  section at the bottom of this file.

The numbered items below correspond exactly to the Phase 4 brief
(`A1, A2, A3, B1, B2, B3, B4`) so you can cross-reference the diff
without hunting.

---

## B3 · Plant identification — decision matrix

Today, plant identification is a deterministic stub
(`StubPlantIdPredictor` in `backend/models/plant_id_model.py`) that
locks every prediction to **cucumber** but already emits the full
structured `PlantIdPrediction` shape (`species_id`, `common_name`,
`scientific_name`, `family`, `confidence`, `source`, `raw`). This
keeps the rest of the pipeline (care recommendations, plant profile,
unified `/report`) honest while we choose a real backend.

Three realistic options were evaluated for the next iteration:

| Axis                    | **PlantNet API**                                      | **iNaturalist API**                                     | **HuggingFace local plant classifier**                      |
|-------------------------|-------------------------------------------------------|---------------------------------------------------------|--------------------------------------------------------------|
| Approach                | Public REST API; ~1 M species; ~30k images/day curated | Crowd-sourced computer-vision endpoint over Seek/CV model | Pretrained ViT / EfficientNet on PlantVillage / PlantCLEF    |
| Best-case accuracy      | ~80–90% top-5 on common species (PlantNet papers)     | ~70–85% top-5 (community-tuned; varies by taxa)         | ~85–95% top-1 on training distribution; degrades out-of-set  |
| Free-tier cost          | Free for ≤500 req/day per project, key required       | Free, soft rate-limited (~60 req/min)                   | Free runtime; only HF inference fees if hosted               |
| Latency (p50)           | ~600–1200ms (Europe egress)                           | ~800–1500ms                                             | ~150–400ms locally · ~600–900ms via HF Inference API         |
| Container size impact   | **0 MB** (network only)                               | **0 MB** (network only)                                 | +300–800 MB for weights + torch/transformers                  |
| Key requirement         | API key (free tier)                                   | None for read; key required for vision endpoint         | None (weights bundled or fetched at runtime)                  |
| Integration effort      | Low — 1 class + 1 env var                              | Low — 1 class + 1 env var; weaker response schema       | Medium — model resolver + ONNX/torch dep + cold-start tuning  |
| Reliability             | Hosted, SLA-less but stable                            | Hosted but rate-limited and intermittent                | Self-hosted ⇒ no external dep, but operator owns model rot   |
| Privacy / portability   | Sends image to PlantNet servers                       | Sends image to iNaturalist servers                      | Image never leaves the container                              |
| Demo-fit (Railway free) | Excellent                                              | Good                                                    | Risky — pushes container past Railway free-tier image budget |

### Recommendation — **PlantNet API**

For the academic Railway demo, **PlantNet API** is the right choice:

1. **Zero container-size impact** — Railway's free tier hates 800 MB
   PyTorch wheels; PlantNet is a pure HTTP call so the existing
   ~150 MB FastAPI image stays unchanged.
2. **Best-in-class accuracy for common edible/garden species** — the
   PlantVision demo focuses on cucumber, tomato, pepper, lettuce,
   basil, strawberry. Those are all over-represented in PlantNet's
   training set.
3. **Lowest integration cost** — one new class
   (`PlantNetPredictor`), one env var (`PLANT_ID_API_KEY`), and the
   existing pluggable seam (`get_plant_id_predictor()`) already
   exists. No schema changes, no migration.
4. **Stays online when local model would not** — the stub fallback
   already in `get_plant_id_predictor()` means a PlantNet outage
   doesn't take `/predict` down with it.

iNaturalist is a fine second choice if PlantNet's free quota becomes
a blocker; the HF local route should be revisited only once the demo
graduates to a paid hosting tier with more disk and RAM.

### Wiring sketch (NOT implemented in this PR)

A future PR that turns this recommendation into code would look like
this — no other module needs to change.

1. **`.env.example`** — add two variables (default to empty so the
   stub stays the default):

   ```dotenv
   # plantnet | inaturalist | hf_local | stub
   PLANT_ID_MODEL=stub
   PLANT_ID_API_KEY=
   ```

2. **`backend/models/plant_id_model.py`** — add a new class next to
   `StubPlantIdPredictor`:

   ```python
   class PlantNetPredictor(PlantIdPredictor):
       def __init__(self, api_key: str):
           self._api_key = api_key
           self._endpoint = "https://my-api.plantnet.org/v2/identify/all"

       def predict(self, image_bytes: bytes) -> PlantIdPrediction:
           # 1) POST image multipart with self._api_key
           # 2) Map PlantNet's `bestMatch` → species_id via
           #    services.species_taxonomy.lookup_by_scientific_name
           # 3) Return PlantIdPrediction(..., source="plantnet", raw=raw_resp)
           ...
   ```

3. **`get_plant_id_predictor()`** — add a third branch above the
   existing fallback:

   ```python
   if backend == "plantnet":
       key = (os.getenv("PLANT_ID_API_KEY") or "").strip()
       if key:
           try:
               return PlantNetPredictor(key)
           except Exception as exc:  # noqa: BLE001
               log.warning("PlantNet init failed: %s — falling back to stub", exc)
       else:
           log.warning("PLANT_ID_MODEL=plantnet but PLANT_ID_API_KEY is empty")
   return StubPlantIdPredictor()
   ```

4. **`backend/services/species_taxonomy.py`** — add a
   `lookup_by_scientific_name(name: str) -> SpeciesEntry | None` helper
   so PlantNet's `bestMatch.species.scientificNameWithoutAuthor` maps
   onto our 6 known species without a separate mapping table.

5. **Tests** — `backend/tests/test_plant_id.py` already exercises the
   stub. Add `test_plantnet_predictor.py` with `httpx_mock` to assert
   request shape + the mapping helper. Keep the stub the default in
   CI (`PLANT_ID_MODEL` unset) so CI does not need a key.

No other file needs to change. The `/predict` and `/report` endpoints
do not know which predictor is active.

---

## B4 · Multi-tenant schema audit

### Status of existing tables (read from `supabase/migrations/0001_init.sql`
and `0003_audit_log.sql`)

| Table              | Tenant column        | Status                                        |
|--------------------|----------------------|-----------------------------------------------|
| `zones`            | _none_               | **Gap** — shared today via slug uniqueness; either add `user_slug` or namespace `slug` (e.g. `<user>:<zone>`). |
| `devices`          | _none directly_      | **Gap** — devices inherit a zone, but zones aren't tenant-scoped yet. |
| `sensor_readings`  | `user_slug` ✅         | OK. Already filtered in repo layer.            |
| `scan_results`     | `user_slug` ✅         | OK. Already filtered in repo layer.            |
| `analytics_events` | `zone_slug` only      | **Partial** — has `zone_slug` but no `user_slug`. Acceptable in single-tenant mode; add `user_slug` for B/D rollout. |
| `audit_log`        | `actor` (free text)   | OK for operator-facing logs; the `actor` column already exists and is filled with the request's `user_id` or client IP. |
| `assistant_logs`   | _none_                | **Gap** — only `zone_slug`. Add `user_slug` when Auth lands. |

**Today's user model.** The whole frontend pins `user_id="demo_user"`
(`frontend/mobile-app/config.js` + every `api.js` call site). The
backend treats this as the canonical key on `sensor_readings` and
`scan_results`. That makes the existing tables already multi-tenant-
ready for the two highest-traffic write paths.

### Index audit

Common multi-tenant lookups today:

* `sensor_readings`: `(user_slug, recorded_at desc)` — used by
  `sensor_repo.latest_for_user` (Batch D will introduce this).
* `scan_results`: `(user_slug, created_at desc)` — used by
  `scans_repo.history_for_user`.
* `scan_results`: `(user_slug, plant_id, created_at desc)` — used by
  `analytics_store.get_latest_scan_for_plant`.
* `audit_log`: `(actor, created_at desc)` — operator
  postmortem queries.

The Phase 2 schema only indexes `(zone_slug, recorded_at desc)` /
`(zone_slug, created_at desc)` / `(created_at desc)`. Single-zone
demo traffic is fast, but a real multi-tenant rollout would table-scan
without per-user indexes.

`supabase/migrations/0004_multitenant_indexes.sql` (created in this
PR) adds these indexes with `CREATE INDEX IF NOT EXISTS`. The
migration is intentionally **not applied** by any script — it's
checked in and ready to apply manually (or via Batch D's wiring).

### How Batch D will flip `demo_user` → real `user_slug`

These steps are scoped here so the reviewer can scan them at a glance,
but **none of them ship today**:

1. Land Supabase Auth on the frontend (Batch D scope). The Auth event
   gives us a stable `user_id` per signed-in operator.
2. Replace every `window.PLANT_USER_ID = "demo_user"` site with a
   getter that reads from the active Supabase session. The
   `api.js` call sites already encode `user_id`, so no contract
   changes.
3. Apply `supabase/migrations/0004_multitenant_indexes.sql` against
   production Supabase (idempotent — `CREATE INDEX IF NOT EXISTS`).
4. Add `user_slug` columns to `zones`, `devices`, `analytics_events`,
   `assistant_logs` in a `0005_tenant_columns.sql` migration. Each
   add is a default-`'demo_user'` non-null column so existing rows
   keep working.
5. Wrap `garden_management.list_zones` / `list_devices` /
   `analytics_*` to filter by `user_slug` from the request (currently
   they are global). Frontend already passes `user_id` on the high-
   traffic paths.
6. Enable Postgres RLS on the tenant-scoped tables with a policy of
   `user_slug = auth.jwt() ->> 'user_id'`.

That's the entire Batch D rollout. Nothing in Batches A+B blocks it.

---

## What's still gated on sign-off

These items are explicitly **not** part of this PR. They each require
the user's explicit go-ahead because they introduce one or more of:
new third-party API keys, durable data-migration steps, or auth flows
that change the operator-facing UX.

* **Batch C — Supabase Storage for scan thumbnails.** Today scan
  thumbnails live on Railway's ephemeral disk under `backend/uploads`.
  This is fine for a demo (lost on every redeploy, see DEPLOY.md §8).
  A future PR would swap the saved-image path for a Supabase
  Storage bucket with signed URLs.
* **Batch C — Real Plant ID API integration.** The decision matrix
  above picks PlantNet, but the implementation, env keys, and tests
  are out of scope until you confirm "yes, integrate PlantNet" and
  share a key (or grant a test key per environment).
* **Batch D — Supabase Auth.** All five operator pages currently
  pin to `demo_user`. Adding Auth changes the topbar (sign-in chip),
  the session-identity inputs on Settings, and how `api.js` resolves
  `PLANT_USER_ID`.
* **Batch D — Full multi-tenant rollout.** The schema audit above
  lists the exact steps. No data migration runs without sign-off.

When you're ready to start any of these, ping back with the green-
light and we'll scope a focused PR for each (each one is a single-
batch PR — they don't bundle).
