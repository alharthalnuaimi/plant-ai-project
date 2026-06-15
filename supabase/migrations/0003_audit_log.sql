-- =====================================================================
-- PlantVision — Phase 3 audit log
-- ---------------------------------------------------------------------
-- Adds a single durable audit table for:
--   * sensor pipeline retries / failures (mirrors core.retry telemetry)
--   * /predict and /report invocations (request_id + outcome + latency)
--   * /care lookups
--   * /sensor validation rejections (already mirrored to analytics_events,
--     but audit_log lets ops slice by actor/route without joining)
--
-- Why a separate table:
--   * analytics_events is user-facing (powers the activity feed).
--   * audit_log is *operator-facing* (powers /health/sensor history,
--     postmortems, retention purges).
--   * This separation lets each table evolve independently.
--
-- All inserts go through services/audit_log.py which silently degrades
-- to a memory ring buffer when persistence is unavailable.
-- =====================================================================

create extension if not exists "pgcrypto";

create table if not exists public.audit_log (
    id              uuid primary key default gen_random_uuid(),
    event_type      text not null,                       -- e.g. 'retry', 'predict', 'report', 'care', 'sensor_validation_failed'
    severity        text not null default 'info',        -- 'info' | 'warning' | 'error' | 'critical'
    operation       text,                                -- e.g. 'sensor_repo.insert_reading'
    request_id      text,
    actor           text,                                -- user_id when known; otherwise client IP
    zone_slug       text,
    device_slug     text,
    plant_id        text,
    outcome         text,                                -- 'success' | 'retry' | 'recovered' | 'failed' | 'rejected'
    elapsed_ms      double precision,
    error_class     text,
    error_message   text,
    payload_json    jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now()
);

create index if not exists audit_log_recent_idx     on public.audit_log(created_at desc);
create index if not exists audit_log_event_idx      on public.audit_log(event_type, created_at desc);
create index if not exists audit_log_severity_idx   on public.audit_log(severity, created_at desc);
create index if not exists audit_log_operation_idx  on public.audit_log(operation, created_at desc);
create index if not exists audit_log_request_idx    on public.audit_log(request_id);

-- Suggested retention policy (run on a schedule outside this migration):
--
--   delete from public.audit_log
--    where severity = 'info'
--      and created_at < now() - interval '14 days';
--
--   delete from public.audit_log
--    where created_at < now() - interval '90 days';
