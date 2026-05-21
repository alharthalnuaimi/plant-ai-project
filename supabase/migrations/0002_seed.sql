-- =====================================================================
-- PlantVision — Seed demo data (idempotent)
-- ---------------------------------------------------------------------
-- Provides the three default zones the frontend expects out-of-the-box,
-- so a fresh DB still feels alive without requiring user input.
-- =====================================================================

insert into public.zones (slug, name, status, latitude, longitude, plants_count)
values
    ('zone_alpha', 'Zone Alpha', 'HEALTHY', 32.0853, 34.7818, 48),
    ('zone_beta',  'Zone Beta',  'WARNING', 32.0900, 34.7900, 36),
    ('zone_gamma', 'Zone Gamma', 'HEALTHY', 32.0800, 34.7700, 24)
on conflict (slug) do nothing;

insert into public.devices (zone_id, slug, device_name, ip_address, status, metadata_json)
select z.id, 'esp32_001', 'Main ESP32 Node', '192.168.1.42', 'OFFLINE', '{"firmware":"v1.0.0"}'::jsonb
from public.zones z where z.slug = 'zone_alpha'
on conflict (slug) do nothing;
