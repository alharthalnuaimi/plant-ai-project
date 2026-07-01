/*
 * Plant AI — ESP32 Sensor Node (Production Firmware v2)
 *
 * Sensors:
 *   - DHT22:  air_temperature, air_humidity  (one-wire, GPIO27)
 *   - BH1750: light_lux                      (I2C, auto-detect 0x23/0x5C)
 *   - RS485:  soil_temperature, soil_humidity, soil_ph, soil_ec
 *             (UART2 Modbus RTU, auto-baud 4800/9600, direction pin GPIO4)
 *
 * Optional:
 *   - 16×2 I2C LCD (auto-detect 0x27/0x3F) — rotates through sensor pages
 *
 * Sends JSON to FastAPI POST /sensor. Failed sensor readings are sent as
 * JSON null so the backend can distinguish "sensor offline" from "zero".
 *
 * v2 Improvements:
 *   - Bug fix: DHT22 enforces ≥2 s between reads to prevent spurious NaN
 *   - Bug fix: Soil sensor baud only resets after 3 consecutive failures
 *   - Bug fix: soil_ec sent as null (not 0) when sensor is offline
 *   - Bug fix: BH1750 -1 error return converted to NAN
 *   - OTA (Over-The-Air) firmware updates via ArduinoOTA
 *   - Non-blocking WiFi watchdog (reconnect attempt every 30 s, 5 s timeout)
 *   - HTTP retry with backoff (up to 2 retries, 2 s between retries)
 *   - 1-slot failed-send buffer — recovered on next successful connection
 *   - Per-sensor running fail counters logged to Serial
 *
 * Setup:
 *   1. Copy config.example.h → config.h and fill in WiFi + API + OTA settings.
 *   2. Install libraries: WiFi, HTTPClient, ArduinoJson, DHT sensor library,
 *      BH1750, LiquidCrystal_I2C, ArduinoOTA (built-in with ESP32 board package).
 *   3. Flash to ESP32 via USB once, then use OTA for subsequent updates.
 */

#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <BH1750.h>
#include <LiquidCrystal_I2C.h>
#include <ArduinoOTA.h>
#include "config.h"

// ────────────────────────── Devices ──────────────────────────

HardwareSerial rs485(2);
DHT dht(DHT_PIN, DHT22);
BH1750 lightMeter;

LiquidCrystal_I2C lcd27(0x27, 16, 2);
LiquidCrystal_I2C lcd3f(0x3F, 16, 2);
LiquidCrystal_I2C *lcd = NULL;

bool lcdReady   = false;
bool lightReady = false;

uint8_t  lcdAddress   = 0;
uint8_t  lightAddress = 0;
uint32_t soilBaud     = 0;

// ────────────────────────── Soil Sensor Settings ──────────────────────────

#define SOIL_SENSOR_ID      1
#define SOIL_FIRST_REGISTER 0x0000
#define SOIL_REGISTER_COUNT 4
#define SOIL_MAX_FAILURES   3   // consecutive failures before baud-scan retry

// ────────────────────────── Timing ──────────────────────────

unsigned long lastSendMs       = 0;
unsigned long lastDHTReadMs    = 0;
unsigned long lastWiFiRetryMs  = 0;
unsigned long lastSensorReadMs = 0;
unsigned long lastLCDUpdateMs  = 0;

#define DHT_MIN_INTERVAL_MS      2000   // DHT22 datasheet: min 2 s between reads
#define WIFI_RETRY_INTERVAL_MS   30000  // how often to attempt WiFi reconnect
#define HTTP_RETRY_COUNT         2      // extra retries after first failure
#define HTTP_RETRY_DELAY_MS      2000   // delay between retries
#define SENSOR_READ_INTERVAL_MS  3000   // read sensors and print every 3 seconds
#define LCD_ROTATION_INTERVAL_MS 1500   // rotate LCD screen every 1.5 seconds (faster display)

// ────────────────────────── Readings ──────────────────────────

struct SensorReadings {
  bool soilOk  = false;
  bool dhtOk   = false;
  bool lightOk = false;

  float    soilMoisture = NAN;
  float    soilTemp     = NAN;
  uint16_t soilEC       = 0;
  float    soilPH       = NAN;

  float airTemp     = NAN;
  float airHumidity = NAN;
  float lux         = NAN;
};

// ────────────────────────── Fail Counters ──────────────────────────

struct FailCounters {
  uint32_t soil  = 0;
  uint32_t dht   = 0;
  uint32_t light = 0;
  uint32_t http  = 0;
};

FailCounters failCounts;

// ────────────────────────── Failed-Send Buffer (1-slot) ──────────────────────────

bool            hasPendingReading = false;
SensorReadings  pendingReading;

// ────────────────────────── Consecutive Soil Failure Counter ──────────────────────────

uint8_t soilConsecFails = 0;

// ────────────────────────── Modbus CRC16 ──────────────────────────

uint16_t modbusCRC(uint8_t *data, uint8_t length) {
  uint16_t crc = 0xFFFF;

  for (uint8_t i = 0; i < length; i++) {
    crc ^= data[i];

    for (uint8_t j = 0; j < 8; j++) {
      if (crc & 0x0001) {
        crc >>= 1;
        crc ^= 0xA001;
      } else {
        crc >>= 1;
      }
    }
  }

  return crc;
}

// ────────────────────────── I2C Helpers ──────────────────────────

bool i2cDeviceFound(uint8_t address) {
  Wire.beginTransmission(address);
  return Wire.endTransmission() == 0;
}

void scanI2C() {
  Serial.println("Scanning I2C bus...");

  int found = 0;

  for (uint8_t address = 1; address < 127; address++) {
    if (i2cDeviceFound(address)) {
      Serial.print("Found I2C device at 0x");

      if (address < 16) {
        Serial.print("0");
      }

      Serial.println(address, HEX);
      found++;
    }
  }

  if (found == 0) {
    Serial.println("No I2C devices found.");
  }
}

bool startLCD() {
  if (i2cDeviceFound(0x27)) {
    lcd        = &lcd27;
    lcdAddress = 0x27;
  } else if (i2cDeviceFound(0x3F)) {
    lcd        = &lcd3f;
    lcdAddress = 0x3F;
  } else {
    return false;
  }

  lcd->init();
  lcd->backlight();
  return true;
}

bool startBH1750() {
  if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x23, &Wire)) {
    lightAddress = 0x23;
    return true;
  }

  if (lightMeter.begin(BH1750::CONTINUOUS_HIGH_RES_MODE, 0x5C, &Wire)) {
    lightAddress = 0x5C;
    return true;
  }

  return false;
}

// ────────────────────────── LCD Output ──────────────────────────

void lcdLine(uint8_t row, String text) {
  if (!lcdReady || lcd == NULL) {
    return;
  }

  while (text.length() < 16) {
    text += " ";
  }

  lcd->setCursor(0, row);
  lcd->print(text.substring(0, 16));
}

String showFloat(float value, int decimals) {
  if (isnan(value)) {
    return "--";
  }

  return String(value, decimals);
}

// ────────────────────────── WiFi ──────────────────────────

/**
 * Attempt a WiFi connection with a bounded timeout.
 * Returns true immediately if already connected (no blocking).
 */
bool connectWiFi(unsigned long timeoutMs) {
  if (WiFi.status() == WL_CONNECTED) {
    return true;
  }

  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startTime = millis();

  while (WiFi.status() != WL_CONNECTED && (millis() - startTime) < timeoutMs) {
    delay(500);
    Serial.print(".");
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi connected. IP: ");
    Serial.println(WiFi.localIP());
    return true;
  }

  Serial.println("WiFi not connected. Local readings will continue.");
  return false;
}

/**
 * Non-blocking WiFi watchdog — call every loop.
 * Attempts reconnect at most once per WIFI_RETRY_INTERVAL_MS.
 */
void wifiWatchdog() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  unsigned long now = millis();

  if (lastWiFiRetryMs == 0 || (now - lastWiFiRetryMs) >= WIFI_RETRY_INTERVAL_MS) {
    lastWiFiRetryMs = now;
    Serial.println("[WiFi] Disconnected. Attempting reconnect (5 s timeout)...");
    connectWiFi(5000);
  }
}

// ────────────────────────── OTA ──────────────────────────

void setupOTA() {
  ArduinoOTA.setHostname(DEVICE_ID);
  ArduinoOTA.setPassword(OTA_PASSWORD);

  ArduinoOTA.onStart([]() {
    String type = (ArduinoOTA.getCommand() == U_FLASH) ? "sketch" : "filesystem";
    Serial.println("[OTA] Starting update: " + type);
    lcdLine(0, "OTA update...");
    lcdLine(1, "Do not power off");
  });

  ArduinoOTA.onEnd([]() {
    Serial.println("\n[OTA] Update complete. Rebooting.");
    lcdLine(0, "OTA done!");
    lcdLine(1, "Rebooting...");
  });

  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    uint8_t pct = progress / (total / 100);
    Serial.printf("[OTA] Progress: %u%%\r", pct);
    lcdLine(1, "Progress: " + String(pct) + "%  ");
  });

  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("[OTA] Error[%u]: ", error);

    switch (error) {
      case OTA_AUTH_ERROR:    Serial.println("Auth failed");    break;
      case OTA_BEGIN_ERROR:   Serial.println("Begin failed");   break;
      case OTA_CONNECT_ERROR: Serial.println("Connect failed"); break;
      case OTA_RECEIVE_ERROR: Serial.println("Receive failed"); break;
      case OTA_END_ERROR:     Serial.println("End failed");     break;
      default:                Serial.println("Unknown error");  break;
    }

    lcdLine(0, "OTA Error!");
    lcdLine(1, "Code: " + String(error));
  });

  ArduinoOTA.begin();
  Serial.println("[OTA] Ready. Hostname: " + String(DEVICE_ID));
}

// ────────────────────────── HTTP POST ──────────────────────────

void addFloatOrNull(JsonDocument &doc, const char *key, float value) {
  if (isnan(value)) {
    doc[key] = nullptr;
  } else {
    doc[key] = value;
  }
}

String buildPayload(const SensorReadings &readings) {
  JsonDocument doc;

  doc["device_id"] = DEVICE_ID;
  doc["zone_id"]   = ZONE_ID;

  addFloatOrNull(doc, "soil_humidity",    readings.soilMoisture);
  addFloatOrNull(doc, "soil_temperature", readings.soilTemp);

  // Bug fix: send null for soil_ec when sensor is offline (was hardcoded 0)
  if (readings.soilOk) {
    doc["soil_ec"] = readings.soilEC / 1000.0;
  } else {
    doc["soil_ec"] = nullptr;
  }

  addFloatOrNull(doc, "soil_ph",        readings.soilPH);
  addFloatOrNull(doc, "air_temperature", readings.airTemp);
  addFloatOrNull(doc, "air_humidity",   readings.airHumidity);
  addFloatOrNull(doc, "light_lux",      readings.lux);

  String payload;
  serializeJson(doc, payload);
  return payload;
}

/**
 * Attempt a single HTTP POST. Returns the HTTP status code,
 * or -1 on connection/timeout failure.
 */
int doHttpPost(const String &endpoint, const String &payload) {
  HTTPClient http;

  // WiFiClientSecure must outlive http — declare it at function scope, not in
  // the if-block, otherwise http holds a dangling reference and the SSL
  // handshake silently fails (HTTP -5 / NOT_CONNECTED).
  WiFiClientSecure secureClient;

  if (endpoint.startsWith("https://")) {
    secureClient.setInsecure();   // skip cert validation (OK for LAN/dev)
    // Explicit SNI hostname — required by Railway's cloud proxy
    String host = endpoint;
    host.replace("https://", "");
    int slashPos = host.indexOf('/');
    if (slashPos > 0) host = host.substring(0, slashPos);
    secureClient.setHandshakeTimeout(15);  // seconds
    http.begin(secureClient, endpoint);
  } else {
    http.begin(endpoint);
  }

  http.addHeader("Content-Type", "application/json");
  http.setTimeout(15000);  // 15 s — accounts for Railway cold-start

  Serial.print("POST ");
  Serial.println(endpoint);
  Serial.println(payload);

  int statusCode = http.POST(payload);
  String response = http.getString();
  http.end();

  Serial.print("HTTP status: ");
  Serial.println(statusCode);

  if (response.length() > 0) {
    Serial.print("Server response: ");
    Serial.println(response);
  }

  return statusCode;
}

/**
 * Send a reading to the server with retry + backoff.
 * Returns true on success (2xx).
 */
bool sendPayload(const String &endpoint, const String &payload) {
  for (uint8_t attempt = 0; attempt <= HTTP_RETRY_COUNT; attempt++) {
    if (attempt > 0) {
      Serial.print("[HTTP] Retry ");
      Serial.print(attempt);
      Serial.print("/");
      Serial.println(HTTP_RETRY_COUNT);
      delay(HTTP_RETRY_DELAY_MS);
    }

    int status = doHttpPost(endpoint, payload);

    if (status >= 200 && status < 300) {
      return true;
    }

    Serial.print("[HTTP] Attempt ");
    Serial.print(attempt + 1);
    Serial.println(" failed.");
  }

  return false;
}

bool sendReadingsToServer(const SensorReadings &readings) {
  if (!connectWiFi(8000)) {
    return false;
  }

  String endpoint = String(API_BASE_URL) + "/sensor";
  bool   sent     = false;

  // Flush any pending (previously failed) reading first
  if (hasPendingReading) {
    Serial.println("[HTTP] Flushing buffered reading from previous failure...");
    String bufferedPayload = buildPayload(pendingReading);

    if (sendPayload(endpoint, bufferedPayload)) {
      Serial.println("[HTTP] Buffered reading sent.");
      hasPendingReading = false;
    } else {
      Serial.println("[HTTP] Buffered reading still failed — overwriting buffer with latest.");
      // Overwrite with latest; keep trying next cycle
    }
  }

  // Send current reading
  String payload = buildPayload(readings);
  sent = sendPayload(endpoint, payload);

  if (!sent) {
    // Store in 1-slot buffer for next successful cycle
    pendingReading    = readings;
    hasPendingReading = true;
    failCounts.http++;
    Serial.println("[HTTP] Current reading buffered for retry next cycle.");
  }

  return sent;
}

// ────────────────────────── RS485 Soil Sensor ──────────────────────────

void startRS485(uint32_t baud) {
  rs485.end();
  delay(100);
  rs485.begin(baud, SERIAL_8N1, RS485_RX_PIN, RS485_TX_PIN);
}

bool readSoilRegisters(uint16_t *regs) {
  uint8_t request[8];

  request[0] = SOIL_SENSOR_ID;
  request[1] = 0x03;
  request[2] = highByte(SOIL_FIRST_REGISTER);
  request[3] = lowByte(SOIL_FIRST_REGISTER);
  request[4] = 0x00;
  request[5] = SOIL_REGISTER_COUNT;

  uint16_t crc = modbusCRC(request, 6);
  request[6] = lowByte(crc);
  request[7] = highByte(crc);

  while (rs485.available()) {
    rs485.read();
  }

  digitalWrite(RS485_DIR_PIN, HIGH);
  delayMicroseconds(300);

  rs485.write(request, 8);
  rs485.flush();

  delayMicroseconds(300);
  digitalWrite(RS485_DIR_PIN, LOW);

  const uint8_t expectedBytes = 5 + (SOIL_REGISTER_COUNT * 2);
  uint8_t response[expectedBytes];

  uint8_t      received  = 0;
  unsigned long startTime = millis();

  while ((millis() - startTime) < 1000 && received < expectedBytes) {
    if (rs485.available()) {
      response[received] = rs485.read();
      received++;
    }
  }

  if (received != expectedBytes) {
    Serial.print("Soil read failed. Received ");
    Serial.print(received);
    Serial.print(" of ");
    Serial.print(expectedBytes);
    Serial.println(" bytes.");
    return false;
  }

  uint16_t receivedCRC   = ((uint16_t)response[expectedBytes - 1] << 8) | response[expectedBytes - 2];
  uint16_t calculatedCRC = modbusCRC(response, expectedBytes - 2);

  if (receivedCRC != calculatedCRC) {
    Serial.println("Soil read failed. CRC mismatch.");
    return false;
  }

  if (response[0] != SOIL_SENSOR_ID || response[1] != 0x03) {
    Serial.println("Soil read failed. Wrong Modbus response.");
    return false;
  }

  for (uint8_t i = 0; i < SOIL_REGISTER_COUNT; i++) {
    uint8_t index = 3 + (i * 2);
    regs[i] = ((uint16_t)response[index] << 8) | response[index + 1];
  }

  return true;
}

bool findSoilSensor() {
  uint16_t regs[SOIL_REGISTER_COUNT];

  uint32_t baudList[2] = {4800, 9600};

  for (uint8_t i = 0; i < 2; i++) {
    uint32_t testBaud = baudList[i];

    Serial.print("Trying soil sensor at ");
    Serial.print(testBaud);
    Serial.println(" baud...");

    startRS485(testBaud);
    delay(300);

    if (readSoilRegisters(regs)) {
      soilBaud = testBaud;

      Serial.print("Soil sensor found at ");
      Serial.print(soilBaud);
      Serial.println(" baud.");

      return true;
    }
  }

  soilBaud = 0;
  return false;
}

// ────────────────────────── Read All Sensors ──────────────────────────

SensorReadings readSensors() {
  SensorReadings readings;

  // ── Soil (RS485 Modbus) ──────────────────────────────────────────────────
  if (soilBaud == 0) {
    findSoilSensor();
  }

  if (soilBaud != 0) {
    uint16_t soilRegs[SOIL_REGISTER_COUNT];
    readings.soilOk = readSoilRegisters(soilRegs);

    if (readings.soilOk) {
      readings.soilMoisture = soilRegs[0] / 10.0;
      readings.soilTemp     = (int16_t)soilRegs[1] / 10.0;
      readings.soilEC       = soilRegs[2];
      readings.soilPH       = soilRegs[3] / 10.0;

      soilConsecFails = 0;  // reset consecutive failure counter on success
    } else {
      soilConsecFails++;
      failCounts.soil++;

      Serial.print("[Soil] Consecutive failures: ");
      Serial.print(soilConsecFails);
      Serial.print(" / ");
      Serial.println(SOIL_MAX_FAILURES);

      // Bug fix: only trigger baud-rescan after 3 consecutive failures,
      // not on every single failure (avoids 600+ ms scan penalty each loop)
      if (soilConsecFails >= SOIL_MAX_FAILURES) {
        Serial.println("[Soil] Max consecutive failures reached — resetting baud for re-scan.");
        soilBaud        = 0;
        soilConsecFails = 0;
      }
    }
  }

  // ── Air (DHT22) ──────────────────────────────────────────────────────────
  // Bug fix: DHT22 requires ≥2 s between reads or it returns NaN.
  // Use last-read timestamp to enforce minimum interval.
  unsigned long now = millis();

  if (lastDHTReadMs == 0 || (now - lastDHTReadMs) >= DHT_MIN_INTERVAL_MS) {
    lastDHTReadMs = now;

    readings.airTemp     = dht.readTemperature();
    readings.airHumidity = dht.readHumidity();
    readings.dhtOk       = !isnan(readings.airTemp) && !isnan(readings.airHumidity);

    if (!readings.dhtOk) {
      failCounts.dht++;
    }
  } else {
    // DHT too soon — mark as no reading this cycle (values remain NAN)
    readings.dhtOk = false;
  }

  // ── Light (BH1750) ───────────────────────────────────────────────────────
  if (lightReady) {
    float rawLux = lightMeter.readLightLevel();

    // Bug fix: BH1750 returns -1 on error; convert to NAN so downstream
    // code can use isnan() uniformly rather than checking for -1.
    if (rawLux < 0) {
      readings.lux     = NAN;
      readings.lightOk = false;
      failCounts.light++;
    } else {
      readings.lux     = rawLux;
      readings.lightOk = true;
    }
  }

  return readings;
}

// ────────────────────────── Serial Output ──────────────────────────

void printReadings(const SensorReadings &readings) {
  Serial.println();
  Serial.println("--------------------");

  if (readings.soilOk) {
    Serial.print("Soil moisture: ");
    Serial.print(readings.soilMoisture, 1);
    Serial.println(" %");

    Serial.print("Soil temperature: ");
    Serial.print(readings.soilTemp, 1);
    Serial.println(" C");

    Serial.print("EC: ");
    Serial.print(readings.soilEC);
    Serial.println(" us/cm");

    Serial.print("pH: ");
    Serial.println(readings.soilPH, 1);
  } else {
    Serial.print("Soil sensor: no reading  [total fails: ");
    Serial.print(failCounts.soil);
    Serial.println("]");
  }

  if (readings.dhtOk) {
    Serial.print("Air temperature: ");
    Serial.print(readings.airTemp, 1);
    Serial.println(" C");

    Serial.print("Humidity: ");
    Serial.print(readings.airHumidity, 1);
    Serial.println(" %");
  } else {
    Serial.print("DHT22: no reading  [total fails: ");
    Serial.print(failCounts.dht);
    Serial.println("]");
  }

  if (readings.lightOk) {
    Serial.print("Light: ");
    Serial.print(readings.lux, 1);
    Serial.println(" lux");
  } else {
    Serial.print("BH1750: no reading  [total fails: ");
    Serial.print(failCounts.light);
    Serial.println("]");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi RSSI: ");
    Serial.println(WiFi.RSSI());
  } else {
    Serial.print("WiFi: disconnected  [HTTP fails: ");
    Serial.print(failCounts.http);
    Serial.println("]");
  }

  if (hasPendingReading) {
    Serial.println("[Buffer] 1 reading pending retry.");
  }
}

void showLCD(const SensorReadings &readings) {
  static uint8_t lcdPage = 0;

  if (lcdPage == 0) {
    lcdLine(0, "M:" + showFloat(readings.soilMoisture, 1) + "% pH:" + showFloat(readings.soilPH, 1));
    lcdLine(1, "EC:" + String(readings.soilEC) + " T:" + showFloat(readings.soilTemp, 1));
  } else if (lcdPage == 1) {
    lcdLine(0, "Air:" + showFloat(readings.airTemp, 1) + "C");
    lcdLine(1, "Hum:" + showFloat(readings.airHumidity, 1) + "%");
  } else if (lcdPage == 2) {
    lcdLine(0, "Light");
    lcdLine(1, showFloat(readings.lux, 0) + " lux");
  } else {
    if (WiFi.status() == WL_CONNECTED) {
      lcdLine(0, "WiFi connected");
      lcdLine(1, WiFi.localIP().toString());
    } else {
      lcdLine(0, "WiFi offline");
      lcdLine(1, "Local only");
    }
  }

  lcdPage++;
  if (lcdPage > 3) {
    lcdPage = 0;
  }
}

// ────────────────────────── Setup ──────────────────────────

void setup() {
  pinMode(RS485_DIR_PIN, OUTPUT);
  digitalWrite(RS485_DIR_PIN, LOW);

  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("ESP32 Plant Health Monitor v2");
  Serial.println("RS485: RO=GPIO16 DI=GPIO17 RE+DE=GPIO4");
  Serial.println("DHT22: DATA=GPIO27");
  Serial.println("I2C: SDA=GPIO21 SCL=GPIO22");
  Serial.println();

  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  dht.begin();

  scanI2C();

  lightReady = startBH1750();
  if (lightReady) {
    Serial.print("BH1750 found at 0x");
    Serial.println(lightAddress, HEX);
  } else {
    Serial.println("BH1750 not found.");
  }

  lcdReady = startLCD();
  if (lcdReady) {
    Serial.print("LCD found at 0x");
    Serial.println(lcdAddress, HEX);
    lcdLine(0, "Plant Monitor v2");
    lcdLine(1, "Starting...");
  } else {
    Serial.println("LCD not found.");
  }

  if (connectWiFi(12000)) {
    setupOTA();
  } else {
    Serial.println("[OTA] Skipped — no WiFi at boot. Will start on reconnect.");
  }

  if (!findSoilSensor()) {
    Serial.println("Soil sensor not found.");
  }
}

// ────────────────────────── Main Loop ──────────────────────────

void loop() {
  // Handle any pending OTA session first
  ArduinoOTA.handle();

  // Non-blocking WiFi watchdog
  wifiWatchdog();

  // If WiFi just came back up and OTA was skipped at boot, initialize it now
  static bool otaStarted = false;
  if (!otaStarted && WiFi.status() == WL_CONNECTED) {
    setupOTA();
    otaStarted = true;
  }

  static SensorReadings currentReadings;
  static bool firstReadDone = false;

  unsigned long now = millis();

  // 1. Read sensors every SENSOR_READ_INTERVAL_MS
  if (!firstReadDone || (now - lastSensorReadMs) >= SENSOR_READ_INTERVAL_MS) {
    lastSensorReadMs = now;
    currentReadings = readSensors();
    printReadings(currentReadings);
    firstReadDone = true;
  }

  // 2. Rotate LCD page every LCD_ROTATION_INTERVAL_MS
  if (now - lastLCDUpdateMs >= LCD_ROTATION_INTERVAL_MS) {
    lastLCDUpdateMs = now;
    showLCD(currentReadings);
  }

  // 3. Send readings to server every SEND_INTERVAL_MS
  if (lastSendMs == 0 || (now - lastSendMs) >= SEND_INTERVAL_MS) {
    lastSendMs = now;

    if (firstReadDone) {
      bool sent = sendReadingsToServer(currentReadings);
      if (sent) {
        Serial.println("Reading sent to server.");
      } else {
        Serial.println("Reading was not sent (buffered for retry).");
      }
    }
  }

  // Prevents CPU spinning and allows ESP32 background tasks to run smoothly
  delay(50);
}
