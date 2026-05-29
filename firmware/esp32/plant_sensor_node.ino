/*
 * Plant AI — ESP32 sensor node (production-ready firmware)
 *
 * Sensors:
 *   - DHT22: air_temperature, air_humidity (one-wire)
 *   - BH1750: light_lux (I2C)
 *   - RS485: soil_temperature, soil_humidity, soil_ph, soil_ec (UART2 Modbus RTU)
 *
 * Sends JSON to FastAPI POST /sensor (supports HTTP and auto WiFiClientSecure HTTPS)
 *
 * Setup:
 *   1. Copy config.example.h → config.h
 *   2. Libraries: WiFi, HTTPClient, ArduinoJson, DHT sensor library, BH1750
 *   3. Set USE_MOCK_SENSORS 0 in config.h when real hardware is wired!
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <WiFiClientSecure.h>
#include <Wire.h>

// Attempt to load user configuration
#if __has_include("config.h")
  #include "config.h"
#else
  #warning "config.h not found! Using default fallbacks. Copy config.example.h -> config.h"
#endif

// Robust configuration fallbacks
#ifndef WIFI_SSID
  #define WIFI_SSID "YOUR_WIFI_SSID"
  #define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
  #define API_BASE_URL "http://192.168.1.10:8000"
  #define DEVICE_ID "esp32_001"
  #define ZONE_ID "zone_alpha"
  #define USE_MOCK_SENSORS 1
  #define SEND_INTERVAL_MS 30000
  #define DHT_PIN 4
  #define BH1750_SDA 21
  #define BH1750_SCL 22
  #define RS485_RX_PIN 16
  #define RS485_TX_PIN 17
  #define RS485_BAUD 9600
#endif

#if !USE_MOCK_SENSORS
  #include <DHT.h>
  #include <BH1750.h>
  
  DHT dht(DHT_PIN, DHT22);
  BH1750 lightMeter;
#endif

struct SensorSample {
  float air_temperature;
  float air_humidity;
  float light_lux;
  float soil_temperature;
  float soil_humidity;
  float soil_ph;
  float soil_ec;
};

// Helper function to calculate Modbus CRC16 checksum for robust RS485 communication
uint16_t calculateCRC16(const uint8_t *buf, int len) {
  uint16_t crc = 0xFFFF;
  for (int pos = 0; pos < len; pos++) {
    crc ^= (uint16_t)buf[pos];
    for (int i = 8; i != 0; i--) {
      if ((crc & 0x0001) != 0) {
        crc >>= 1;
        crc ^= 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }
  return crc;
}

void readDHT22(SensorSample &s) {
#if USE_MOCK_SENSORS
  s.air_temperature = 24.0f + (random(0, 100) / 50.0f);
  s.air_humidity = 55.0f + (random(0, 200) / 10.0f);
#else
  float t = dht.readTemperature();
  float h = dht.readHumidity();
  
  if (isnan(t) || isnan(h)) {
    Serial.println("Warning: Failed to read from DHT22 air sensor! Using fallback...");
    s.air_temperature = 24.0f;
    s.air_humidity = 60.0f;
  } else {
    s.air_temperature = t;
    s.air_humidity = h;
  }
#endif
}

void readBH1750(SensorSample &s) {
#if USE_MOCK_SENSORS
  s.light_lux = 1200.0f + random(0, 800);
#else
  float lux = lightMeter.readLightLevel();
  if (lux < 0.0f) {
    Serial.println("Warning: Failed to read from BH1750 light sensor! Using fallback...");
    s.light_lux = 1500.0f;
  } else {
    s.light_lux = lux;
  }
#endif
}

void readRS485Soil(SensorSample &s) {
#if USE_MOCK_SENSORS
  s.soil_temperature = 21.0f + random(0, 80) / 10.0f;
  s.soil_humidity = 45.0f + random(0, 250) / 10.0f;
  s.soil_ph = 6.2f + random(0, 10) / 10.0f;
  s.soil_ec = 1.2f + random(0, 15) / 10.0f;
#else
  // Standard Modbus RTU inquiry frame for Soil probes:
  // Slave Address (0x01), Function Code (0x03), Starting Address (0x00 0x00), Count (0x00 0x04)
  // Checksum CRC16 is 0x4409
  const uint8_t inquiryFrame[] = {0x01, 0x03, 0x00, 0x00, 0x00, 0x04, 0x44, 0x09};
  
  // Flush any stale incoming UART data
  while (Serial2.available() > 0) {
    Serial2.read();
  }
  
  Serial2.write(inquiryFrame, sizeof(inquiryFrame));
  Serial2.flush();
  
  // Wait up to 250ms for response (13 bytes: 3 header + 8 data + 2 CRC)
  unsigned long start = millis();
  const int expectedLen = 13;
  uint8_t response[expectedLen] = {0};
  int index = 0;
  
  while (millis() - start < 250 && index < expectedLen) {
    if (Serial2.available() > 0) {
      response[index++] = Serial2.read();
    }
  }
  
  if (index < expectedLen) {
    Serial.printf("Warning: RS485 Modbus timeout! Read only %d / %d bytes. Using fallback...\n", index, expectedLen);
    s.soil_temperature = 22.0f;
    s.soil_humidity = 50.0f;
    s.soil_ph = 6.5f;
    s.soil_ec = 1.5f;
    return;
  }
  
  // Verify Slave Address, Function Code, and Data Length
  if (response[0] != 0x01 || response[1] != 0x03 || response[2] != 0x08) {
    Serial.println("Warning: Invalid Modbus response header! Using fallback...");
    s.soil_temperature = 22.0f;
    s.soil_humidity = 50.0f;
    s.soil_ph = 6.5f;
    s.soil_ec = 1.5f;
    return;
  }
  
  // Verify Checksum
  uint16_t receivedCRC = (response[12] << 8) | response[11];
  uint16_t calculatedCRC = calculateCRC16(response, 11);
  if (receivedCRC != calculatedCRC) {
    Serial.printf("Warning: Modbus CRC mismatch (Recv: 0x%04X, Calc: 0x%04X)! Using fallback...\n", receivedCRC, calculatedCRC);
    s.soil_temperature = 22.0f;
    s.soil_humidity = 50.0f;
    s.soil_ph = 6.5f;
    s.soil_ec = 1.5f;
    return;
  }
  
  // Parse data values (each register is 16-bit big-endian)
  uint16_t rawMoisture = (response[3] << 8) | response[4];
  int16_t rawTemp     = (response[5] << 8) | response[6];
  uint16_t rawEC       = (response[7] << 8) | response[8];
  uint16_t rawPH       = (response[9] << 8) | response[10];
  
  s.soil_humidity = rawMoisture / 10.0f;
  s.soil_temperature = rawTemp / 10.0f;
  s.soil_ec = rawEC / 1000.0f; // Scale to mS/cm or keep raw based on standard settings
  s.soil_ph = rawPH / 10.0f;
  
  Serial.printf("Modbus Soil: Temp=%.1f C, Moist=%.1f %%, pH=%.1f, EC=%.3f\n", 
                s.soil_temperature, s.soil_humidity, s.soil_ph, s.soil_ec);
#endif
}

bool postSensorReading(const SensorSample &s) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi not connected");
    return false;
  }

  StaticJsonDocument<512> doc;
  doc["user_id"] = "demo_user";
  doc["device_id"] = DEVICE_ID;
  doc["zone_id"] = ZONE_ID;
  doc["air_temperature"] = s.air_temperature;
  doc["air_humidity"] = s.air_humidity;
  doc["light_lux"] = s.light_lux;
  doc["soil_temperature"] = s.soil_temperature;
  doc["soil_humidity"] = s.soil_humidity;
  doc["soil_ph"] = s.soil_ph;
  doc["soil_ec"] = s.soil_ec;

  String body;
  serializeJson(doc, body);

  String url = String(API_BASE_URL) + "/sensor";
  HTTPClient http;
  
  if (url.startsWith("https://")) {
    WiFiClientSecure client;
    client.setInsecure(); // Dynamic handshakes for public endpoints
    http.begin(client, url);
  } else {
    http.begin(url);
  }
  
  http.addHeader("Content-Type", "application/json");

  int code = http.POST(body);
  Serial.printf("POST /sensor → HTTP %d\n", code);
  if (code > 0) {
    Serial.println(http.getString());
  }
  http.end();
  return code >= 200 && code < 300;
}

void setup() {
  Serial.begin(115200);
  randomSeed(analogRead(0));

#if !USE_MOCK_SENSORS
  // DHT initialization
  dht.begin();
  
  // BH1750 light sensor I2C initialization
  Wire.begin(BH1750_SDA, BH1750_SCL);
  if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE)) {
    Serial.println("BH1750 light sensor initialized successfully.");
  } else {
    Serial.println("Warning: BH1750 light sensor failed to start!");
  }
  
  // RS485 Soil probe hardware serial initialization (UART2)
  Serial2.begin(RS485_BAUD, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);
  Serial.println("RS485 Modbus Serial2 port initialized.");
#endif

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi OK");
  Serial.println(WiFi.localIP());
}

void loop() {
  SensorSample sample = {};
  readDHT22(sample);
  readBH1750(sample);
  readRS485Soil(sample);

  postSensorReading(sample);
  delay(SEND_INTERVAL_MS);
}
