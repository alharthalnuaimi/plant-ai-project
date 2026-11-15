# Gemini-only AI architecture

Status: implemented on branch `feat/gemini-only-ai` (2026-11-14).

All plant intelligence (photo diagnosis, species identification, symptom
recognition, reasoning, explanations and treatment advice) now runs on the
Google Gemini API through the official `google-genai` SDK, using one
server-side key (`GEMINI_API_KEY`). The production API loads no local AI
model and never substitutes canned or random output when Gemini fails.

## 1. Original architecture (verified in source before the migration)

| Concern | Where it lived | Behaviour |
|---|---|---|
| YOLOv8 initialisation | `backend/models/disease_model.py` → `YoloVisionPredictor` (`ultralytics.YOLO(weights)`) | Lazy, per species, via `SpeciesAwareVisionPredictor` |
| Weight loading | `services/model_registry.py` + `artifacts/registry.json`, `*_WEIGHTS_PATH` env | Only if the registry marked the weights `local_model_trusted` and the `.pt` file existed |
| Image diagnosis | `services/prediction.py::run_vision_prediction` → `ModelManager.get_vision_model()` | Used by `/predict`, `/analyze`, image `/report` |
| Fallback when no YOLO | `MultiProviderConsensusPredictor` (Gemini/Claude/GPT/Kimi/Roboflow vote) → **`StubVisionPredictor`** | The stub picked a **pseudo-random disease label** from a hash of the image bytes, with a made-up confidence |
| Species identification | `models/plant_id_model.py` → Pl@ntNet API, falling back to `StubPlantIdPredictor` | The stub always answered "cucumber" at 0.55 |
| Gemini usage | `models/llama_model.py::GeminiClient` | `/chat` reasoning, plus a "second opinion" on `/predict` (`services/gemini_second_opinion.py`) that keyword-scanned free text for agree/disagree |
| Reasoning engine | `/chat` → Gemini; `/analyze` → **Ollama** (`LlamaClient`) | Both fell back to `fallback_narrative()` — a fixed rule-based paragraph — on any error or missing key |
| Results to frontend | `VisionResult` JSON (`schemas/contracts.py`); `app.js::showPredictResult` then auto-calls `/chat` | `/chat` payload filled missing sensors with **made-up defaults** (50 % / 25 °C / 60 %) |
| Sensors | `POST /sensor` → `sensor_store` (+ Postgres); `/predict` snapshots the latest reading into scan metadata | Only 3 of 7 readings reached the reasoning prompt |
| Survival | `services/survival.py` — deterministic weighted rule score | Unchanged by this migration |
| Other local AI paths | Ollama (`OLLAMA_BASE_URL`), `test_model.py`, `training/`, `scripts/retrain.py`, `scripts/run_eval.py` | Training/eval only, not request paths |

Note: the README described YOLOv8 as the live detector, but with no trusted
weights deployed, production scans were actually going to the multi-provider
vote or the random stub.

## 2. New architecture

```
Frontend (mobile-app)          never sees the key
   │  POST /predict, /chat, /analyze, /report
   ▼
FastAPI backend
   │
   ▼
services/gemini/  ── Gemini Intelligence Service
   ├── config.py      env → GeminiConfig (key hidden from repr)
   ├── client.py      google-genai client, timeout, retries+backoff, error mapping,
   │                  safety/truncation detection, token-usage logging
   ├── images.py      validate, EXIF-rotate, downscale, JPEG re-encode (strips EXIF/GPS)
   ├── diagnosis.py   image (+ species hint) → GeminiDiagnosis   [cached by image hash]
   ├── reasoning.py   diagnosis × sensors × survival × question → GeminiReasoning   [never cached]
   ├── prompts.py     system prompts, PROMPT_VERSION
   ├── schemas.py     response contracts + consistency rules
   └── errors.py      structured AppErrors
   │
   ▼
Structured results → existing response shapes → frontend
```

| Route | Flow |
|---|---|
| `POST /predict` | validate upload → **Gemini diagnosis** → persist image → sensor snapshot → health score → `VisionResult` |
| `POST /chat` | newest device reading (or client values) → rule-based survival (only if inputs exist) → **Gemini reasoning** |
| `POST /analyze` | **Gemini diagnosis** → survival → **Gemini reasoning** (with the photo) |
| `POST /report` (image) | **Gemini diagnosis** → health + care plan |
| `GET /health/services`, `/models/health` | Gemini configured/models; YOLO, Ollama, Pl@ntNet reported `disabled` |

### Diagnosis contract (`GeminiDiagnosis`)

`image_quality` (good/acceptable/poor/unusable) · `plant_identification`
(`is_plant`, names, family, genus, confidence) · `diagnosis` (`status`:
healthy/diseased/stressed/uncertain/not_assessable, `primary_condition`,
`category`, `confidence`, `severity`) · `observations[]` (each `confirmed` or
`possible`) · `alternative_diagnoses[]` · `uncertainties[]` ·
`stress_signal` · `summary`.

Honesty rules, enforced in code after validation
(`enforce_diagnosis_consistency`), which only ever remove claims:

- not a plant or unusable image → `not_assessable`, no condition, no confidence, no species;
- `uncertain` → no primary condition;
- `diseased`/`stressed` without a named condition → `uncertain`.

Mapping onto the existing `VisionResult`: `disease`/`class_name` via the
existing taxonomy; `confidence` = Gemini's self-reported value (0.0 when
null) with `metadata.confidence_kind = "model_self_reported"`;
`accepted` = assessable and confidence ≥ threshold; `plant.source = "gemini"`
(or `"manual"` when the user locked a species); `gemini_agrees = null`
(hides the obsolete disagreement banner); the full assessment is in
`metadata.gemini_diagnosis`, call stats in `metadata.gemini`.

### Reasoning contract (`GeminiReasoning`)

`answer`, `summary`, `disease_explanation`, `possible_causes[]`,
`environmental_analysis{temperature, humidity, soil_conditions, light_conditions}`,
`recommendations[]`, `treatment_plan[]`, `prevention[]`, `urgent_actions[]`,
`urgency` (low/moderate/high/critical), `recovery_assessment{estimate:
good/fair/poor/null, confidence, explanation}`. No numeric survival
probabilities are requested from the model. `/chat` keeps
`reply`/`recommendation`/`source`/`survival_probability`/`breakdown` and adds
`reasoning`, `model` and `sensor_context`.

### Sensor context

Every reading (air temperature, air humidity, soil temperature, soil
moisture, pH, EC, light) is passed with its timestamp and age. When the
request names a user/zone/device, the newest stored reading wins over values
the client sent. Missing values are `null` — the frontend no longer
substitutes defaults.

## 3. Failure handling

| Condition | HTTP | `error` | Retried? |
|---|---|---|---|
| Key missing | 503 | `gemini_not_configured` | no |
| Key invalid / forbidden | 502 | `gemini_auth_failed` | no |
| Daily / billing quota exhausted | 429 | `gemini_quota_exceeded` | no |
| Per-minute rate limit | 429 | `gemini_rate_limited` | yes |
| 5xx / overloaded | 503 | `gemini_unavailable` | yes |
| Timeout | 504 | `gemini_timeout` | yes |
| Network error | 503 | `gemini_network_error` | yes |
| Safety block (prompt or candidate) | 422 | `gemini_safety_blocked` | no |
| Non-JSON / schema-invalid / truncated / empty | 502 | `gemini_invalid_response` | no |
| Model not available to the key | 503 | `gemini_model_unavailable` | once, on the fallback model |
| Other bad request | 400 | `gemini_bad_request` | no |
| Unreadable / tiny image | 400 | `invalid_image` | — (Gemini not called) |
| Upload over `MAX_UPLOAD_BYTES` | 413 | `image_too_large` | — (Gemini not called) |

Retries: up to `GEMINI_MAX_RETRIES` (default 1), on `GEMINI_FALLBACK_MODEL`
(default `gemini-3.5-flash-lite`) when set, with backoff and jitter. The whole
call, retry included, stops after `GEMINI_DEADLINE_SECONDS` (default 30); each
attempt is capped at `GEMINI_TIMEOUT_SECONDS` (default 20) and the time left,
but never under 10 s, the API's minimum, so the worst case is about 32 s.
The SDK's own retrying is switched off so attempts are not multiplied. Error bodies are
`{"error", "message", "request_id"}`; messages never contain the key or the
upstream response. On `/predict` the diagnosis runs **before** anything is
persisted, so a failed scan leaves no record and can simply be retried.

## 4. Cost and performance controls

- Images are downscaled to `GEMINI_MAX_IMAGE_SIDE` (1536 px) and re-encoded as JPEG (quality 85) before upload.
- Identical photos reuse the cached diagnosis (`GEMINI_CACHE_TTL_SECONDS`, keyed by image SHA-256 + model + prompt version + species hint). Sensor-dependent reasoning is never cached.
- Each call logs operation, model, attempts, latency and prompt/output/total token counts — never the key, prompt, image or answer.
- Models, temperatures, output-token limit and thinking budget are configurable per environment.

## 5. What was kept but switched off

Per the project owner's instruction, legacy code was **kept in the repo but
disconnected**, not deleted:

- `backend/models/disease_model.py` (YOLO router, multi-provider predictor, random stub),
  `models/llama_model.py` (Ollama client, old Gemini wrapper, `fallback_narrative`),
  `models/plant_id_model.py` (Pl@ntNet + stub), `services/model_manager.py`,
  `services/gemini_second_opinion.py` — each carries a `DISABLED` header.
- `artifacts/`, `training/`, `scripts/`, `dataset/`, `test_model.py` — unchanged (training/evaluation only).
- `/admin/providers` multi-provider annotation tooling — still available for building training data; its Gemini agent now uses the shared client. It is not used for user scans.

`test_production_modules_do_not_import_legacy_local_ai` fails the build if
any route or service imports those modules again, and
`test_no_local_model_runs_on_any_ai_route` trips if any of them is called.

To bring YOLO back deliberately, add an explicit, documented code path (not
an automatic fallback) and update those two tests.

## 6. Testing

- `backend/tests/test_gemini_migration.py` — client init, missing key, diagnosis,
  reasoning, invalid image, invalid/blocked responses, quota, rate limit, network,
  timeout, auth, sensor context, frontend contract, no-local-model and no-fallback
  guarantees. Uses `tests/gemini_fakes.py` (installed for every test by
  `conftest.py`), so no network or quota is used.
- `backend/tests/test_gemini_live.py` — optional real-API check:
  `RUN_GEMINI_LIVE_TESTS=1 python -m pytest backend/tests/test_gemini_live.py`.
- `frontend/tests/api.test.js` — `node --test frontend/tests/api.test.js`.

## 7. Limitations

- Gemini's confidence values are self-assessments, not calibrated probabilities.
- The rule-based survival score still uses the diagnosis label/confidence as an input; it is a heuristic score.
- The diagnosis cache is per-process memory; multiple workers each keep their own.
- Species mapping to the care catalog only covers catalogued species; others map to `unknown` (care templates fall back accordingly).
- Gemini calls are synchronous SDK calls run in FastAPI's threadpool.

## References

- Gemini API docs: https://ai.google.dev/gemini-api/docs
- API keys: https://ai.google.dev/gemini-api/docs/api-key
- Image understanding: https://ai.google.dev/gemini-api/docs/image-understanding
- Structured output: https://ai.google.dev/gemini-api/docs/structured-output
- Rate limits: https://ai.google.dev/gemini-api/docs/rate-limits
- Troubleshooting: https://ai.google.dev/gemini-api/docs/troubleshooting
