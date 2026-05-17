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

## Backend endpoints

### POST /sensor

Accepts JSON from the ESP32 (or curl/Swagger for testing):

```json
{
  "device_id": "esp32_001",
  "plant_id": "cucumber_001",
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

Returns:

```json
{
  "ok": true,
  "source": "live",
  "reading": { ... }
}
```

If nothing was posted yet: `"source": "none"`, `"reading": null`.

Data is kept **in memory** until the server restarts.

## Manual test (PowerShell curl)

Start backend, then:

```powershell
curl -X POST "http://127.0.0.1:8000/sensor" `
  -H "Content-Type: application/json" `
  -d "{\"device_id\":\"esp32_001\",\"plant_id\":\"cucumber_001\",\"air_temperature\":34.5,\"air_humidity\":42,\"light_lux\":700,\"soil_temperature\":28.2,\"soil_humidity\":41,\"soil_ph\":6.4,\"soil_ec\":1.8}"

curl "http://127.0.0.1:8000/sensor/latest"
```

Or use http://127.0.0.1:8000/docs → **POST /sensor** and **GET /sensor/latest**.

Example test payload (stress case):

```json
{
  "device_id": "esp32_001",
  "plant_id": "cucumber_001",
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
