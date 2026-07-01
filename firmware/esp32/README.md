# ESP32 Plant Sensor Node — Firmware v2

Reads soil, air, and light sensors and POSTs JSON data to the Plant AI backend every 30 seconds.

---

## Hardware

| Sensor  | Interface | Pins |
|---------|-----------|------|
| DHT22   | One-wire  | GPIO27 |
| BH1750  | I2C       | SDA=GPIO21, SCL=GPIO22 |
| RS485 soil probe | UART2 Modbus RTU | RO=GPIO16, DI=GPIO17, RE+DE=GPIO4 |
| LCD 16×2 (optional) | I2C | 0x27 or 0x3F (auto-detected) |

---

## Project Structure (PlatformIO)

```
firmware/esp32/
├── platformio.ini          # Board, framework, library config
├── src/
│   └── main.cpp            # Main firmware source
├── include/
│   ├── config.h            # ← YOUR SETTINGS (not committed)
│   └── config.example.h   # Template — copy to config.h
├── plant_sensor_node.ino   # Legacy Arduino IDE file (kept for reference)
└── README.md
```

---

## Setup

### 1. Install PlatformIO
- Install [VS Code](https://code.visualstudio.com/) + [PlatformIO extension](https://platformio.org/install/ide?install=vscode), **or**
- Use PlatformIO CLI: `pip install platformio`

### 2. Configure credentials
```bash
cp include/config.example.h include/config.h
# Then edit include/config.h with your WiFi, API URL, and OTA password
```

### 3. First flash (USB)
```bash
# From firmware/esp32/
pio run --target upload
```

### 4. Monitor serial output
```bash
pio device monitor
```

---

## OTA Updates (After First USB Flash)

Once the device is on WiFi, you can flash wirelessly:

1. Find the ESP32's IP address in the serial monitor output.
2. In `platformio.ini`, uncomment and set:
   ```ini
   upload_protocol = espota
   upload_port     = 192.168.0.XXX   ; your ESP32's IP
   upload_flags    = --auth=plantai123
   ```
3. Run: `pio run --target upload`

Or use PlatformIO IDE: the ESP32 will appear as a network port in the upload menu.

---

## Libraries (auto-installed by PlatformIO)

| Library | Version |
|---------|---------|
| `adafruit/DHT sensor library` | ^1.4.6 |
| `adafruit/Adafruit Unified Sensor` | ^1.1.14 |
| `claws/BH1750` | ^1.3.0 |
| `marcoschwartz/LiquidCrystal_I2C` | ^1.1.4 |
| `bblanchon/ArduinoJson` | ^7.0.4 |

`WiFi`, `HTTPClient`, `WiFiClientSecure`, and `ArduinoOTA` are built into the ESP32 Arduino framework — no extra install needed.

---

## v2 Changes

- **Bug fix**: DHT22 now enforces ≥2 s between reads (prevents spurious NaN)
- **Bug fix**: Soil baud-rate rescan only triggered after 3 consecutive failures (not every failure)
- **Bug fix**: `soil_ec` sent as `null` when sensor is offline (was `0`, indistinguishable from a real zero)
- **Bug fix**: BH1750 `-1` error converted to `NAN` for consistent `isnan()` checks
- **OTA**: Wireless firmware updates via ArduinoOTA
- **WiFi watchdog**: Non-blocking reconnect every 30 s — sensor reads continue offline
- **HTTP retry**: Up to 2 retries with 2 s backoff on failure
- **Failed-send buffer**: Last dropped reading recovered on next successful send
- **Fail counters**: Per-sensor running failure counts printed to Serial
