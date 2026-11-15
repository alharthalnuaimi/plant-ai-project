# 🌱 Plant AI Project

<div align="center">

![AI](https://img.shields.io/badge/AI-Google%20Gemini-green)
![Backend](https://img.shields.io/badge/Backend-FastAPI-blue)
![Frontend](https://img.shields.io/badge/Frontend-Mobile%20Web-orange)
![IoT](https://img.shields.io/badge/IoT-ESP32-red)
![Sensors](https://img.shields.io/badge/Sensors-DHT22%20%7C%20BH1750%20%7C%20RS485-purple)
![Status](https://img.shields.io/badge/Status-Working%20MVP-success)
![Python](https://img.shields.io/badge/Python-3.10+-yellow)

# Intelligent Plant Monitoring & Disease Detection System

AI-powered agriculture monitoring system combining **Computer Vision**, **IoT Sensors**, **FastAPI Backend**, and **Mobile Frontend Integration**.

</div>

---

# 📌 Overview

Plant AI Project is a smart agriculture MVP that helps monitor plant health using AI-powered disease detection and environmental sensor analysis.

The current working MVP supports:

✅ Plant disease diagnosis and species identification from photos using Google Gemini  
✅ Gemini reasoning that cross-references the diagnosis with live sensor data  
✅ Frontend image upload and live prediction  
✅ FastAPI backend (the only component that talks to Gemini)  
✅ Sensor API integration for environmental monitoring  
✅ ESP32 firmware structure for IoT sensors  
✅ Real-time frontend environment data updates  

Future versions will combine:

- plant image analysis
- environmental sensor readings
- survival prediction
- intelligent recommendations
- plant health scoring

---

# ✨ Features

| Feature | Status | Description |
|--------|--------|-------------|
| AI Disease Diagnosis | ✅ Working | Gemini multimodal diagnosis: species, visible symptoms, primary/alternative diagnoses, uncertainties |
| Frontend Scan Upload | ✅ Working | Upload image and receive live AI result |
| FastAPI Backend | ✅ Working | Handles prediction and sensor APIs |
| YOLOv8 Models | ⏸ Disabled | Kept in `backend/models/` and `training/`; not loaded by the API |
| Sensor API | ✅ Working | Accept sensor readings via JSON |
| Frontend Environment Dashboard | ✅ Working | Displays latest sensor/environment values |
| ESP32 Firmware Structure | ✅ Ready | Placeholder firmware for sensor node |
| Survival Prediction | ✅ Working | Calculates plant survival probability using vision and sensor inputs |
| Gemini Plant Assistant | ✅ Working | Structured reasoning over the diagnosis, all sensor readings and the user's question |
| AI Recommendations | ✅ Working | Treatment plan, prevention, urgency and recovery outlook from Gemini |

---

# 🏗 System Architecture

```text
Mobile Frontend
      │
      ├── Scan Plant Image
      ├── Display AI Results
      └── Display Environment Values
              │
              ▼
FastAPI Backend
      │
      ├── /predict
      ├── /sensor
      ├── /sensor/latest
      ├── /survival
      └── /chat
              │
              ▼
Gemini Intelligence Service (backend/services/gemini)
      │
      ├── Gemini Vision Diagnosis  (image → structured JSON)
      ├── Gemini Reasoning         (diagnosis × sensors × question)
      └── Rule-based Survival Score (backend/services/survival.py)
              │
              ▼
ESP32 Sensor Node
      │
      ├── DHT22 (Air Temperature / Humidity)
      ├── BH1750 (Light Intensity)
      └── RS485 Sensor
             ├── Soil Temperature
             ├── Soil Humidity
             ├── pH
             └── EC
🛠 Tech Stack
AI
Google Gemini API (official google-genai SDK) — diagnosis + reasoning
Pillow (image validation / compression)
Training only (not used by the API): YOLOv8 / Ultralytics
Backend
FastAPI
Uvicorn
Pydantic
FastAPI Swagger Docs
Frontend
Mobile web frontend
JavaScript
Node.js local frontend server

Frontend repository contributor:
Mohamed Al-Baqir

Frontend project:
plant-MB

IoT
ESP32
DHT22
BH1750
RS485 sensor
UART / I2C communication
📂 Project Structure
plant-ai-project/
│
├── artifacts/
│   ├── models/
│   │   └── cucumber_yolov8.pt
│   └── registry.json
│
├── backend/
│   ├── config/
│   ├── models/
│   ├── routes/
│   ├── schemas/
│   ├── services/
│   ├── uploads/
│   ├── main.py
│   └── requirements.txt
│
├── frontend/
│   ├── _imports/
│   ├── mobile-app/
│   └── README.md
│
├── firmware/
│   └── esp32/
│       ├── plant_sensor_node.ino
│       ├── config.example.h
│       └── README.md
│
├── dataset/
│   ├── cucumber/
│   ├── classification/
│   ├── yolov8/
│   └── _imports/
│
├── training/
│   ├── configs/
│   └── scripts/
│
├── docs/
│   ├── setup_backend.md
│   ├── setup_frontend.md
│   ├── setup_sensors.md
│   └── team_workflow.md
│
└── README.md

# 🔑 Gemini Configuration

All AI in PlantVision runs on the Google Gemini API: photo diagnosis
(`/predict`, `/analyze`, image `/report`) and reasoning (`/chat`, `/analyze`).
One key powers both, and it lives **only on the backend**.

1. Create a key at https://aistudio.google.com/app/apikey
2. Put it in the repo-root `.env` (copy `.env.example`):

```bash
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

There is no offline fallback: if Gemini is unreachable or the key is
missing, the API returns a structured error such as
`{"error": "gemini_not_configured", "message": "..."}` and the app shows it
so the user can retry. Nothing is made up.

How diagnosis and reasoning work, the error codes and troubleshooting:
[SETUP.md](SETUP.md) and [docs/architecture/gemini-migration.md](docs/architecture/gemini-migration.md).


🚀 Backend Setup


Open CMD:

cd /d D:\plant-ai-project\backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000

Open API docs:

http://127.0.0.1:8000/docs
📱 Frontend Setup

Open second CMD:

cd /d D:\plant-ai-project\frontend\mobile-app
node server.js

Open frontend:

http://localhost:3000

For phone testing:

http://YOUR_PC_IP:3000
🧪 Manual Testing
1. AI Image Prediction Test

Open:

http://127.0.0.1:8000/docs

Test:

POST /predict

Upload plant leaf image.

Expected:

{
  "disease": "--",
  "confidence": --,
  "accepted": --,
  "inference_ms": 100
}
2. Frontend Scan Test

Frontend:

http://localhost:3000

Flow:

Scan
→ upload cucumber image
→ AI prediction
→ disease + confidence shown
3. Sensor API Manual Test

Swagger:

POST /sensor

Example:

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

Then:

GET /sensor/latest

Expected:

source = live

Frontend updates within ~5 seconds.

### 4. Chat Assistant Test

Endpoint:

POST /chat

Example:

```json
{
  "vision": {
    "disease": "rose_nutrient_deficient",
    "confidence": 0.98,
    "stress_hint": "no_strong_visual_stress_signal"
  },
  "sensors": {
    "soil_moisture": 50,
    "temperature": 25,
    "humidity": 60,
    "species": "rose"
  },
  "user_question": "Explain why this disease happens."
}
```

Expected:

- `source: "gemini"`, `reply` (direct answer) and `recommendation`
- `reasoning`: explanation, causes, environmental analysis, treatment plan, prevention, urgency, recovery outlook
- Survival probability (rule-based) when soil moisture, temperature and humidity are provided
- Sensor fields you omit are treated as "no data", never guessed

🌐 Network Testing

Get PC IP:

ipconfig

Example:

192.168.1.20

Use:

Backend:

http://192.168.1.20:8000

Frontend:

http://192.168.1.20:3000

ESP32 sensor API:

http://192.168.1.20:8000/sensor
🔌 Sensor Integration
Current Sensors
DHT22

Measures:

air temperature
air humidity
BH1750

Measures:

light intensity (lux)
RS485 Sensor

Measures:

soil temperature
soil humidity
soil pH
soil EC
📡 Sensor JSON Format
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
👥 Team Workflow
Team Role	Folder
Backend Developers	backend/
Frontend Developers	frontend/mobile-app/
IoT / Sensor Team	firmware/esp32/
AI Model Training	training/
Dataset Management	dataset/
Documentation	docs/
🎯 Current MVP Achievements

✅ Gemini multimodal plant diagnosis (YOLOv8 models kept for training, disabled in the API)
✅ Live backend inference
✅ FastAPI API documentation
✅ Frontend scan integration
✅ Sensor API backend
✅ Environment frontend updates
✅ Team project structure
✅ Gemini-powered plant assistant
✅ Scan-aware chatbot context
✅ Survival probability engine
✅ AI-generated recommendations
✅ Structured, retryable errors instead of fabricated fallback answers

🚀 Future Improvements
AI Improvements
multi-class disease detection
healthy vs diseased classification
disease type classification:
powdery mildew
downy mildew
bacterial wilt
leaf spot
Validation

Create real-world evaluation table:

Image | Expected | Predicted | Confidence | Correct?
Smart Features

Plant Health Score:

Plant Health: 74%
Disease Risk: High
Environment Stress: Medium
Survival Chance: 81%
Recommendation: Reduce heat stress and monitor soil humidity.

This combines:

AI image prediction
sensor readings
survival logic

Future AI

Multi-turn memory
Advanced agronomic reasoning
RAG-based agricultural knowledge retrieval
Multi-language plant assistant
Voice-enabled plant advisor


🏆 Project Evaluation

Student / MVP prototype score:

8.8 / 10

Strengths:

real working MVP
full-stack integration
AI + IoT combination
scalable architecture
clean team organization
💡 Final Vision

Ultimate demo flow:

Scan plant
→ detect disease
→ read sensor values
→ analyze environment stress
→ calculate survival chance
→ generate intelligent recommendation

This would become a strong graduation/project demonstration.



