-- =====================================================================
-- PlantVision — Phase 2 initial schema
-- ---------------------------------------------------------------------
-- Tables (normalized MVP):
--   zones                 - growing zones (alpha/beta/gamma/...)
--   devices               - ESP32 / sensor nodes attached to a zone
--   sensor_readings       - time-series sensor stream from devices
--   scan_results          - YOLO + plant-health enriched scan output
--   analytics_events      - mixed activity feed (scans, alerts, sensors)
--   assistant_logs        - rule-based assistant Q/A history (optional)
--
-- Notes:
--   * UUID primary keys for forward-compatibility.
--   * Timestamps are UTC (timestamptz).
--   * No FK ON DELETE CASCADE on sensor_readings to preserve history
--     even when devices are detached/renamed.
--   * Indexes target the most common access patterns (per-zone,
--     per-device, recent-first activity feed).
-- =====================================================================

create extension if not exists "pgcrypto";

-- ---------- zones -------------------------------------------------------
create table if not exists public.zones (
    id              uuid primary key default gen_random_uuid(),
    slug            text unique not null,
    name            text not null,
    status          text not null default 'HEALTHY',
    latitude        double precision,
    longitude       double precision,
    plants_count    integer not null default 0,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists zones_status_idx on public.zones(status);

-- ---------- devices -----------------------------------------------------
create table if not exists public.devices (
    id              uuid primary key default gen_random_uuid(),
    zone_id         uuid references public.zones(id) on delete set null,
    slug            text unique not null,
    device_name     text not null,
    ip_address      text,
    status          text not null default 'OFFLINE',
    last_seen       timestamptz,
    metadata_json   jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index if not exists devices_zone_idx on public.devices(zone_id);
create index if not exists devices_status_idx on public.devices(status);

-- ---------- sensor_readings --------------------------------------------
create table if not exists public.sensor_readings (
    id              bigserial primary key,
    device_id       uuid references public.devices(id) on delete set null,
    zone_slug       text,
    device_slug     text,
    user_slug       text not null default 'demo_user',
    air_temp        double precision,
    air_humidity    double precision,
    soil_temp       double precision,
    soil_moisture   double precision,
    ph              double precision,
    ec              double precision,
    lux             double precision,
    recorded_at     timestamptz not null default now()
);

create index if not exists sensor_readings_device_idx on public.sensor_readings(device_id, recorded_at desc);
create index if not exists sensor_readings_zone_idx   on public.sensor_readings(zone_slug, recorded_at desc);
create index if not exists sensor_readings_recent_idx on public.sensor_readings(recorded_at desc);

-- ---------- scan_results -----------------------------------------------
create table if not exists public.scan_results (
    id                  uuid primary key default gen_random_uuid(),
    zone_id             uuid references public.zones(id) on delete set null,
    device_id           uuid references public.devices(id) on delete set null,
    zone_slug           text,
    device_slug         text,
    user_slug           text not null default 'demo_user',
    image_path          text,
    prediction_class    text,
    disease_type        text,
    disease             text,
    confidence          double precision,
    accepted            boolean not null default true,
    inference_ms        double precision,
    health_score        integer,
    risk_level          text,
    survival_score      integer,
    recommendation      text,
    model_name          text,
    model_version       text,
    metadata_json       jsonb not null default '{}'::jsonb,
    created_at          timestamptz not null default now()
);

create index if not exists scan_results_zone_idx       on public.scan_results(zone_slug, created_at desc);
create index if not exists scan_results_recent_idx     on public.scan_results(created_at desc);
create index if not exists scan_results_disease_idx    on public.scan_results(disease);

-- ---------- analytics_events -------------------------------------------
create table if not exists public.analytics_events (
    id              uuid primary key default gen_random_uuid(),
    event_type      text not null,
    category        text,
    title           text,
    message         text not null,
    zone_slug       text,
    device_slug     text,
    zone_id         uuid references public.zones(id) on delete set null,
    device_id       uuid references public.devices(id) on delete set null,
    payload_json    jsonb not null default '{}'::jsonb,
    created_at      timestamptz not null default now()
);

create index if not exists analytics_events_recent_idx on public.analytics_events(created_at desc);
create index if not exists analytics_events_type_idx   on public.analytics_events(event_type, created_at desc);
create index if not exists analytics_events_zone_idx   on public.analytics_events(zone_slug, created_at desc);

-- ---------- assistant_logs (optional) ----------------------------------
create table if not exists public.assistant_logs (
    id              uuid primary key default gen_random_uuid(),
    question        text not null,
    response        text not null,
    zone_slug       text,
    zone_id         uuid references public.zones(id) on delete set null,
    created_at      timestamptz not null default now()
);

create index if not exists assistant_logs_recent_idx on public.assistant_logs(created_at desc);

-- ---------- helpers / triggers -----------------------------------------
create or replace function public.touch_updated_at() returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists zones_touch_updated_at on public.zones;
create trigger zones_touch_updated_at
    before update on public.zones
    for each row execute function public.touch_updated_at();

drop trigger if exists devices_touch_updated_at on public.devices;
create trigger devices_touch_updated_at
    before update on public.devices
    for each row execute function public.touch_updated_at();
