# ESP32 sensor node firmware

Starter sketch for the Plant AI sensor integration MVP.

## Hardware

| Sensor | Interface | JSON fields |
|--------|-----------|-------------|
| DHT22 | GPIO | `air_temperature`, `air_humidity` |
| BH1750 | I2C | `light_lux` |
| RS485 soil probe | UART2 | `soil_temperature`, `soil_humidity`, `soil_ph`, `soil_ec` |

## Files

- `plant_sensor_node.ino` — main loop, HTTP POST to backend
- `config.example.h` — copy to `config.h` (keep `config.h` out of git if it has secrets)

## Identity fields (POST /sensor JSON)

| Field | Example | Meaning |
|-------|---------|---------|
| `user_id` | `demo_user` | Operator / account (MVP default) |
| `zone_id` | `zone_alpha` | Growing zone or greenhouse section |
| `device_id` | `esp32_001` | This ESP32 node |

Set `ZONE_ID` and `DEVICE_ID` in `config.h` (from `config.example.h`).

## Backend endpoint

```http
POST http://YOUR_PC_IP:8000/sensor
Content-Type: application/json
```

See `docs/setup_sensors.md` for the full JSON body and testing.

## Mock mode

Set `USE_MOCK_SENSORS 1` in config until wiring and libraries are ready.
