// Copy to config.h and fill in your network + API settings.
// Do not commit config.h with real passwords.

#pragma once

#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// FastAPI backend API endpoint. Examples:
//   - Local LAN dev:   "http://192.168.1.10:8000"
//   - Public Cloud:     "https://your-app.up.railway.app" (automatic HTTPS supported)
#define API_BASE_URL "http://192.168.1.10:8000"

#define DEVICE_ID "esp32_001"
#define ZONE_ID "zone_alpha"

// DHT22 — air temperature + humidity
#define DHT_PIN 4
#define DHT_TYPE DHT22

// BH1750 — light (I2C); set pins per your wiring
#define BH1750_SDA 21
#define BH1750_SCL 22

// RS485 soil probe on UART2
#define RS485_RX_PIN 16
#define RS485_TX_PIN 17
#define RS485_BAUD 9600

// Set 1 to send mock values until sensors are wired
#define USE_MOCK_SENSORS 1

// POST interval (ms)
#define SEND_INTERVAL_MS 30000
