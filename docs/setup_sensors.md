# Sensor setup (ESP32 MVP)

## Sensors

| Sensor | MCU connection | Fields |
|--------|----------------|--------|
| DHT22 | GPIO | `air_temperature`, `air_humidity` |
| BH1750 | I2C | `light_lux` |
| RS485 soil probe | UART2 | `soil_temperature`, `soil_humidity`, `soil_ph`, `soil_ec` |
| ESP32 | Wi-Fi | POST JSON to backend |

Firmware starter: `firmware/esp32/plant_sensor_node.ino`  
Config template: `firmware/esp32/config.example.h` → copy to `config.h`

## MVP identity model

Each sensor reading is tagged with three IDs:

| Field | Meaning | Example |
|-------|---------|---------|
| `user_id` | Account / operator (no auth yet) | `demo_user` |
| `zone_id` | Growing area, greenhouse section, garden zone | `zone_alpha` |
| `device_id` | ESP32 or sensor node hardware | `esp32_001` |

Hierarchy: **user_id → zone_id → device_id**

## Backend endpoints

### POST /sensor

Accepts JSON from the ESP32 (or curl/Swagger for testing):

```json
{
  "user_id": "demo_user",
  "zone_id": "zone_alpha",
  "device_id": "esp32_001",
  "air_temperature": 24.4,
  "air_humidity": 67,
  "light_lux": 1858,
  "soil_temperature": 22.1,
  "soil_humidity": 58,
  "soil_ph": 6.7,
  "soil_ec": 1.9
}
```

Response includes `timestamp` and rule-based `status` (air/soil/light/pH/EC + `overall_environment_status`).

Validation (MVP):

| Field | Range |
|-------|--------|
| `air_temperature` | −40…60 °C |
| `air_humidity` | 0…100 % |
| `light_lux` | ≥ 0 |
| `soil_temperature` | −10…50 °C |
| `soil_humidity` | 0…100 % |
| `soil_ph` | 0…14 |
| `soil_ec` | ≥ 0 mS/cm |

### GET /sensor/latest

Query parameters (all optional, MVP defaults):

| Param | Default |
|-------|---------|
| `user_id` | `demo_user` |
| `zone_id` | `zone_alpha` |
| `device_id` | `esp32_001` |

Example:

```http
GET /sensor/latest?user_id=demo_user&zone_id=zone_alpha&device_id=esp32_001
```

Returns separate fields on `reading` — never a merged id:

```json
{
  "ok": true,
  "source": "live",
  "reading": {
    "user_id": "demo_user",
    "zone_id": "zone_alpha",
    "device_id": "esp32_001",
    "air_temperature": 24.4,
    ...
  }
}
```

If nothing was posted for that triple: `"source": "none"`, `"reading": null`.

Readings are stored in memory under an internal composite key `user_id:zone_id:device_id` (e.g. `demo_user:zone_alpha:esp32_001`). The API always returns `user_id`, `zone_id`, and `device_id` as separate JSON fields.

Data is cleared when the server restarts.

## Manual test (PowerShell curl)

Start backend, then:

```powershell
curl -X POST "http://127.0.0.1:8000/sensor" `
  -H "Content-Type: application/json" `
  -d "{\"user_id\":\"demo_user\",\"zone_id\":\"zone_alpha\",\"device_id\":\"esp32_001\",\"air_temperature\":34.5,\"air_humidity\":42,\"light_lux\":700,\"soil_temperature\":28.2,\"soil_humidity\":41,\"soil_ph\":6.4,\"soil_ec\":1.8}"

curl "http://127.0.0.1:8000/sensor/latest?user_id=demo_user&zone_id=zone_alpha&device_id=esp32_001"
```

Or use http://127.0.0.1:8000/docs → **POST /sensor** and **GET /sensor/latest**.

Example test payload (stress case):

```json
{
  "user_id": "demo_user",
  "zone_id": "zone_alpha",
  "device_id": "esp32_001",
  "air_temperature": 34.5,
  "air_humidity": 42,
  "light_lux": 700,
  "soil_temperature": 28.2,
  "soil_humidity": 41,
  "soil_ph": 6.4,
  "soil_ec": 1.8
}
```

## Frontend

The Home environment strip polls **GET /sensor/latest** every 5 seconds and maps:

| UI | API field |
|----|-----------|
| Temperature | `air_temperature` |
| Humidity | `air_humidity` |
| Light | `light_lux` |
| Soil | `soil_humidity` (%), or `soil_ec` (mS) if humidity is absent |

## Survival note

**POST /survival** still uses `SurvivalSensorInput` (`soil_moisture`, `temperature`, `humidity`).  
**POST /survival/from-latest-sensor** maps the latest ESP reading: `soil_humidity` → moisture, `air_temperature` / `air_humidity` → temp/humidity.

## Connecting Sensors to a Remote Server / Supabase

When deploying physical ESP32 sensors in the field (outside your local network), you have two options for posting telemetry:

### Option A: Deployed FastAPI Backend (Recommended)

You deploy the FastAPI backend to a public hosting provider (e.g., Render, Railway). This keeps your Supabase credentials secure (hidden inside the backend environment variables) and retains real-time alert/event monitoring:

1. Deploy the backend and configure its `.env` variables (`DATABASE_URL`, etc.).
2. In the ESP32 code (`config.h` or `main.cpp`), set the `API_BASE_URL` to your public URL:
   ```cpp
   #define API_BASE_URL "https://your-plantvision-backend.railway.app"
   ```
3. Since FastAPI uses HTTPS, ensure the ESP32 code uses `WiFiClientSecure` or bypasses certificate validation (for testing/development):
   ```cpp
   WiFiClientSecure client;
   client.setInsecure(); // Recommended for development only
   ```

### Option B: Posting Telemetry Directly to Supabase REST API

If you prefer to bypass the FastAPI backend entirely for telemetry, the ESP32 can POST directly to the Supabase Database REST API. Note that this bypasses FastAPI's in-memory event-triggers (like low humidity warnings) unless you handle them in PostgreSQL database triggers or edge functions.

1. **Get your Supabase credentials** from `.env`:
   - URL: `https://<ref>.supabase.co`
   - Anon Key: `sb_publishable_...`
2. **Define target endpoint and headers** in your ESP32 code:
   - URL: `https://<ref>.supabase.co/rest/v1/sensor_readings`
   - Headers:
     - `apikey: <anon-key>`
     - `Authorization: Bearer <anon-key>`
     - `Content-Type: application/json`
     - `Prefer: return=minimal` (optional, to save bandwidth)
3. **Map ESP32 JSON payload** to match the database schema column names:
   ```json
   {
     "user_slug": "demo_user",
     "zone_slug": "zone_alpha",
     "device_slug": "esp32_001",
     "air_temp": 25.4,
     "air_humidity": 38.4,
     "lux": 1200.0,
     "soil_temp": 21.0,
     "soil_moisture": 45.0,
     "ph": 6.5,
     "ec": 1.5
   }
   ```
4. **Example ESP32 connection code snippet**:
   ```cpp
   #include <WiFiClientSecure.h>
   #include <HTTPClient.h>

   bool sendDirectToSupabase(const SensorReadings &readings) {
     WiFiClientSecure client;
     client.setInsecure(); // Or load Supabase Root Certificate (DigiCert)

     HTTPClient http;
     String url = "https://your-project-ref.supabase.co/rest/v1/sensor_readings";
     http.begin(client, url);

     // Required Headers
     http.addHeader("Content-Type", "application/json");
     http.addHeader("apikey", "YOUR_SUPABASE_ANON_KEY");
     http.addHeader("Authorization", "Bearer YOUR_SUPABASE_ANON_KEY");

     // Build JSON Payload matching DB column names
     JsonDocument doc;
     doc["user_slug"] = "demo_user";
     doc["zone_slug"] = ZONE_ID;
     doc["device_slug"] = DEVICE_ID;
     doc["air_temp"] = readings.airTemp;
     doc["air_humidity"] = readings.airHumidity;
     doc["lux"] = readings.lux;
     doc["soil_temp"] = readings.soilTemp;
     doc["soil_moisture"] = readings.soilMoisture;
     doc["ph"] = readings.soilPH;
     doc["ec"] = readings.soilEC;

     String payload;
     serializeJson(doc, payload);

     int code = http.POST(payload);
     http.end();
     return code >= 200 && code < 300;
   }
   ```

