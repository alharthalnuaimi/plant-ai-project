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
