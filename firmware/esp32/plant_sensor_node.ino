/*
 * Plant AI — ESP32 Sensor Node (Production Firmware)
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
 * Setup:
 *   1. Copy config.example.h → config.h and fill in WiFi + API settings.
 *   2. Install libraries: WiFi, HTTPClient, ArduinoJson, DHT sensor library,
 *      BH1750, LiquidCrystal_I2C.
 *   3. Flash to ESP32.
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
#include "config.h"

// ────────────────────────── Devices ──────────────────────────

HardwareSerial rs485(2);
DHT dht(DHT_PIN, DHT22);
BH1750 lightMeter;

LiquidCrystal_I2C lcd27(0x27, 16, 2);
LiquidCrystal_I2C lcd3f(0x3F, 16, 2);
LiquidCrystal_I2C *lcd = NULL;

bool lcdReady = false;
bool lightReady = false;

uint8_t lcdAddress = 0;
uint8_t lightAddress = 0;
uint32_t soilBaud = 0;
unsigned long lastSendMs = 0;

// ────────────────────────── Soil Sensor Settings ──────────────────────────

#define SOIL_SENSOR_ID 1
#define SOIL_FIRST_REGISTER 0x0000
#define SOIL_REGISTER_COUNT 4

// ────────────────────────── Readings ──────────────────────────

struct SensorReadings {
  bool soilOk = false;
  bool dhtOk = false;
  bool lightOk = false;

  float soilMoisture = NAN;
  float soilTemp = NAN;
  uint16_t soilEC = 0;
  float soilPH = NAN;

  float airTemp = NAN;
  float airHumidity = NAN;
  float lux = NAN;
};

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
    lcd = &lcd27;
    lcdAddress = 0x27;
  } else if (i2cDeviceFound(0x3F)) {
    lcd = &lcd3f;
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

// ────────────────────────── HTTP POST ──────────────────────────

void addFloatOrNull(JsonDocument &doc, const char *key, float value) {
  if (isnan(value)) {
    doc[key] = nullptr;
  } else {
    doc[key] = value;
  }
}

bool sendReadingsToServer(const SensorReadings &readings) {
  if (!connectWiFi(8000)) {
    return false;
  }

  JsonDocument doc;

  doc["device_id"] = DEVICE_ID;
  doc["zone_id"] = ZONE_ID;

  addFloatOrNull(doc, "soil_humidity", readings.soilMoisture);
  addFloatOrNull(doc, "soil_temperature", readings.soilTemp);
  doc["soil_ec"] = readings.soilOk ? readings.soilEC / 1000.0 : 0;
  addFloatOrNull(doc, "soil_ph", readings.soilPH);

  addFloatOrNull(doc, "air_temperature", readings.airTemp);
  addFloatOrNull(doc, "air_humidity", readings.airHumidity);

  addFloatOrNull(doc, "light_lux", readings.lux);

  String payload;
  serializeJson(doc, payload);

  String endpoint = String(API_BASE_URL) + "/sensor";

  HTTPClient http;

  if (endpoint.startsWith("https://")) {
    WiFiClientSecure client;
    client.setInsecure();
    http.begin(client, endpoint);
  } else {
    http.begin(endpoint);
  }

  http.addHeader("Content-Type", "application/json");

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

  return statusCode >= 200 && statusCode < 300;
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

  uint8_t received = 0;
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

  uint16_t receivedCRC = ((uint16_t)response[expectedBytes - 1] << 8) | response[expectedBytes - 2];
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

  // Soil (RS485 Modbus)
  if (soilBaud == 0) {
    findSoilSensor();
  }

  if (soilBaud != 0) {
    uint16_t soilRegs[SOIL_REGISTER_COUNT];
    readings.soilOk = readSoilRegisters(soilRegs);

    if (readings.soilOk) {
      readings.soilMoisture = soilRegs[0] / 10.0;
      readings.soilTemp = (int16_t)soilRegs[1] / 10.0;
      readings.soilEC = soilRegs[2];
      readings.soilPH = soilRegs[3] / 10.0;
    } else {
      soilBaud = 0;
    }
  }

  // Air (DHT22)
  readings.airTemp = dht.readTemperature();
  readings.airHumidity = dht.readHumidity();
  readings.dhtOk = !isnan(readings.airTemp) && !isnan(readings.airHumidity);

  // Light (BH1750)
  if (lightReady) {
    readings.lux = lightMeter.readLightLevel();
    readings.lightOk = readings.lux >= 0;
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
    Serial.println("Soil sensor: no reading");
  }

  if (readings.dhtOk) {
    Serial.print("Air temperature: ");
    Serial.print(readings.airTemp, 1);
    Serial.println(" C");

    Serial.print("Humidity: ");
    Serial.print(readings.airHumidity, 1);
    Serial.println(" %");
  } else {
    Serial.println("DHT22: no reading");
  }

  if (readings.lightOk) {
    Serial.print("Light: ");
    Serial.print(readings.lux, 1);
    Serial.println(" lux");
  } else {
    Serial.println("BH1750: no reading");
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi RSSI: ");
    Serial.println(WiFi.RSSI());
  } else {
    Serial.println("WiFi: disconnected");
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
  Serial.println("ESP32 Plant Health Monitor");
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
    lcdLine(0, "Plant Monitor");
    lcdLine(1, "Starting...");
  } else {
    Serial.println("LCD not found.");
  }

  connectWiFi(12000);

  if (!findSoilSensor()) {
    Serial.println("Soil sensor not found.");
  }
}

// ────────────────────────── Main Loop ──────────────────────────

void loop() {
  SensorReadings readings = readSensors();

  printReadings(readings);
  showLCD(readings);

  unsigned long now = millis();
  if (lastSendMs == 0 || (now - lastSendMs) >= SEND_INTERVAL_MS) {
    lastSendMs = now;

    bool sent = sendReadingsToServer(readings);
    if (sent) {
      Serial.println("Reading sent to server.");
    } else {
      Serial.println("Reading was not sent.");
    }
  }

  delay(3000);
}
