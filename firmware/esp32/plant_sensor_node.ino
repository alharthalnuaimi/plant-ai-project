/*
 * Plant AI — ESP32 sensor node (starter / placeholder)
 *
 * Sensors:
 *   - DHT22: air_temperature, air_humidity
 *   - BH1750: light_lux (I2C)
 *   - RS485: soil_temperature, soil_humidity, soil_ph, soil_ec (UART2)
 *
 * Sends JSON to FastAPI POST /sensor
 *
 * Setup:
 *   1. Copy config.example.h → config.h
 *   2. Libraries: WiFi, HTTPClient, ArduinoJson, DHT, BH1750 (when wired)
 *   3. Set USE_MOCK_SENSORS 0 when hardware is ready
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define API_BASE_URL "http://192.168.1.10:8000"
#define DEVICE_ID "esp32_001"
#define ZONE_ID "zone_alpha"
#define USE_MOCK_SENSORS 1
#define SEND_INTERVAL_MS 30000
#define DHT_PIN 4
#endif

// #include <DHT.h>
// #include <BH1750.h>
// DHT dht(DHT_PIN, DHT22);
// BH1750 lightMeter;

struct SensorSample {
  float air_temperature;
  float air_humidity;
  float light_lux;
  float soil_temperature;
  float soil_humidity;
  float soil_ph;
  float soil_ec;
};

void readDHT22(SensorSample &s) {
#if USE_MOCK_SENSORS
  s.air_temperature = 24.0f + (random(0, 100) / 50.0f);
  s.air_humidity = 55.0f + (random(0, 200) / 10.0f);
#else
  // s.air_temperature = dht.readTemperature();
  // s.air_humidity = dht.readHumidity();
  s.air_temperature = 24.0f;
  s.air_humidity = 60.0f;
#endif
}

void readBH1750(SensorSample &s) {
#if USE_MOCK_SENSORS
  s.light_lux = 1200.0f + random(0, 800);
#else
  // s.light_lux = lightMeter.readLightLevel();
  s.light_lux = 1500.0f;
#endif
}

void readRS485Soil(SensorSample &s) {
#if USE_MOCK_SENSORS
  s.soil_temperature = 21.0f + random(0, 80) / 10.0f;
  s.soil_humidity = 45.0f + random(0, 250) / 10.0f;
  s.soil_ph = 6.2f + random(0, 10) / 10.0f;
  s.soil_ec = 1.2f + random(0, 15) / 10.0f;
#else
  // TODO: Modbus/RS485 on Serial2 (RX=16, TX=17) — parse probe frame
  s.soil_temperature = 22.0f;
  s.soil_humidity = 50.0f;
  s.soil_ph = 6.5f;
  s.soil_ec = 1.5f;
#endif
}

#include <WiFiClientSecure.h>

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
    client.setInsecure();
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

  // dht.begin();
  // Wire.begin(); lightMeter.begin();

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
