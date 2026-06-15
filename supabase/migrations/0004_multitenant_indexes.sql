-- =====================================================================
-- PlantVision — Phase 4 (B4) multi-tenant index pre-work
-- ---------------------------------------------------------------------
-- This migration is intentionally **not applied automatically**. It is
-- checked in alongside the Phase 4 audit (PHASE4.md §B4) so that the
-- exact SQL is in source control and reviewable before Batch D wires
-- in Supabase Auth + real `user_slug` filtering.
--
-- Every statement uses CREATE INDEX IF NOT EXISTS so re-running this
-- file is safe. There is no DDL change that could break Phase 3
-- queries — all of these are additive composite indexes on existing
-- columns.
--
-- Apply manually when ready:
--     psql "$DATABASE_URL" -f supabase/migrations/0004_multitenant_indexes.sql
--
-- Or through scripts/apply_migration_0003.py's pattern in a sibling
-- 0004 script.
-- =====================================================================

-- ---------- sensor_readings -------------------------------------------
-- Hot path: "latest reading for a given operator across all their
-- zones" — needed for the Profile + Assistant aggregation queries that
-- Batch D will introduce.
create index if not exists sensor_readings_user_idx
    on public.sensor_readings(user_slug, recorded_at desc);

-- Hot path: per-operator, per-zone latest reading (Garden page when
-- multiple users exist).
create index if not exists sensor_readings_user_zone_idx
    on public.sensor_readings(user_slug, zone_slug, recorded_at desc);

-- ---------- scan_results -----------------------------------------------
-- Hot path: per-operator history feed (Phase 3's scans/history already
-- filters by user_slug in the repo layer; this index makes the query
-- index-only).
create index if not exists scan_results_user_idx
    on public.scan_results(user_slug, created_at desc);

-- Hot path: plant profile aggregation — `analytics_store.get_latest_scan_for_plant`
-- filters by (user_slug, plant_id). plant_id is stored inside
-- metadata_json today; once it's promoted to a column in a future
-- migration, replace this with a real composite index.
-- For now, narrow on user_slug to keep page loads sub-second per tenant.
create index if not exists scan_results_user_zone_idx
    on public.scan_results(user_slug, zone_slug, created_at desc);

-- ---------- analytics_events ------------------------------------------
-- analytics_events does not have a user_slug column yet (see
-- PHASE4.md §B4 — Batch D adds it via 0005_tenant_columns.sql).
-- When that lands, append:
--     create index if not exists analytics_events_user_idx
--         on public.analytics_events(user_slug, created_at desc);
-- For now we add an index on (zone_slug, event_type) which already
-- helps the per-zone activity feed.
create index if not exists analytics_events_zone_type_idx
    on public.analytics_events(zone_slug, event_type, created_at desc);

-- ---------- audit_log -------------------------------------------------
-- audit_log already has actor (text) — useful for operator-scoped
-- postmortems ("show me everything actor=demo_user did in the last 24h").
create index if not exists audit_log_actor_idx
    on public.audit_log(actor, created_at desc);

-- ---------- assistant_logs --------------------------------------------
-- assistant_logs does not have a user_slug column today (Batch D
-- territory). Until then, an index on (zone_slug, created_at desc)
-- speeds up the per-zone chat history view.
create index if not exists assistant_logs_zone_idx
    on public.assistant_logs(zone_slug, created_at desc);

-- =====================================================================
-- End of migration. Re-running this file is safe (CREATE INDEX IF NOT
-- EXISTS is idempotent). No data is moved.
-- =====================================================================
