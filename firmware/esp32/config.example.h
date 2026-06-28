// Copy to config.h and fill in your network + API settings.
// Do not commit config.h with real passwords.

#pragma once

// ---------- WiFi ----------
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// ---------- Backend API ----------
// FastAPI backend API endpoint. Examples:
//   - Local LAN dev:   "http://192.168.1.10:8000"
//   - Public Cloud:    "https://your-app.up.railway.app" (automatic HTTPS supported)
#define API_BASE_URL "http://192.168.1.10:8000"

// ---------- Identity ----------
#define DEVICE_ID "esp32_001"
#define ZONE_ID "zone_alpha"

// ---------- Pins ----------

// DHT22 — air temperature + humidity
#define DHT_PIN 27

// BH1750 — light (I2C)
#define I2C_SDA_PIN 21
#define I2C_SCL_PIN 22

// RS485 soil probe on UART2 (Modbus RTU)
#define RS485_RX_PIN 16
#define RS485_TX_PIN 17
#define RS485_DIR_PIN 4      // RE+DE tied together — HIGH=TX, LOW=RX

// ---------- Intervals ----------
// POST interval (ms) — how often to send readings to the backend
#define SEND_INTERVAL_MS 30000
