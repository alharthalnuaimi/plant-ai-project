# Team workflow

Keep each area in its folder so backend, frontend, IoT, and ML work in parallel without mixing concerns.

## Folder ownership

| Folder | Who | Purpose |
|--------|-----|---------|
| `backend/` | Backend / API | FastAPI, YOLO inference, sensor API, survival rules |
| `frontend/mobile-app/` | Frontend | Mobile web UI, scan, environment display |
| `firmware/esp32/` | IoT / sensors | ESP32 sketch, Wi-Fi, POST `/sensor` |
| `dataset/` | ML / data | Raw and organized datasets only |
| `training/` | ML | YOLO training scripts, validation, splits |
| `artifacts/models/` | ML / release | Trained weights (e.g. `cucumber_yolov8.pt`) |
| `docs/` | Everyone | Setup and how we work together |

Do **not** move backend or frontend into new roots. Do **not** commit datasets or large weights unless the team agrees.

## Typical flows

**Backend developer**

1. `docs/setup_backend.md` — run uvicorn, set `YOLO_WEIGHTS_PATH`.
2. Change routes/services under `backend/`; test at `/docs`.
3. Coordinate API contracts with frontend (predict + sensor).

**Frontend developer**

1. `docs/setup_frontend.md` — `node server.js`, set API URL.
2. Work only under `frontend/mobile-app/` for UI.
3. Scan → `POST /predict`; environment strip → `GET /sensor/latest`.

**Sensor / IoT developer**

1. `docs/setup_sensors.md` + `firmware/esp32/README.md`.
2. Flash ESP32, point `API_BASE_URL` at the PC running FastAPI.
3. Verify **POST /sensor** in Swagger before relying on the UI.

**ML / training**

1. Datasets in `dataset/`; scripts in `training/`.
2. Export best weights to `artifacts/models/`.
3. Tell backend to use the new path via `YOLO_WEIGHTS_PATH`.

## MVP identity model

API payloads use three IDs (no database yet):

- `user_id` — who owns the data (default `demo_user`)
- `zone_id` — which growing zone / section (default `zone_alpha`)
- `device_id` — which ESP32 node (e.g. `esp32_001`)

Keep these **separate** — do not merge into one field (e.g. no `user_zone_id`).

Relationships (MVP):

- One user → many zones
- One zone → one user
- One zone → one or more devices
- Sensor reading → `user_id` + `zone_id` + `device_id`
- Vision scan → `user_id` + `zone_id`

Vision scans (`POST /predict`) send `user_id` + `zone_id` as form fields.  
Sensor posts (`POST /sensor`) send all three in JSON.  
`GET /sensor/latest` filters by all three query parameters.

## MVP boundaries (for now)

- No Supabase / DB for sensors (in-memory store).
- No Ollama required for scan or sensor MVP.
- Do not break **POST /predict** when adding sensor features.

## Integration checklist

- [ ] Backend up, `/health` OK
- [ ] `POST /sensor` returns a reading
- [ ] `GET /sensor/latest` shows `source: "live"`
- [ ] Frontend env strip updates
- [ ] Scan still works on a test image
