# 🌱 Plant AI Project

<div align="center">

![AI](https://img.shields.io/badge/AI-YOLOv8%20%7C%20Llama-green)
![Backend](https://img.shields.io/badge/Backend-FastAPI-blue)
![Frontend](https://img.shields.io/badge/Mobile%20App-Frontend-orange)
![Database](https://img.shields.io/badge/Database-Supabase-brightgreen)
![IoT](https://img.shields.io/badge/IoT-ESP32-red)
![Cloud](https://img.shields.io/badge/Cloud-Oracle%20Cloud-lightgrey)
![Status](https://img.shields.io/badge/Status-MVP%20In%20Development-yellow)

### Intelligent Plant Health Monitoring & Disease Detection System

AI-powered agriculture assistant combining **Computer Vision**, **IoT Sensors**, **Backend Intelligence**, and **LLM Reasoning** to monitor plant health and detect disease.

</div>

---

# 📌 Overview

**Plant AI Project** is an AI-powered smart agriculture system designed to monitor plant health, detect disease, analyze environmental conditions, and provide intelligent recommendations.

The system combines:

- 🌿 Plant disease detection using **YOLOv8**
- 🌡 Environmental monitoring using **IoT sensors**
- 🧠 AI reasoning using **Llama / Ollama**
- ⚡ Fast backend processing using **FastAPI**
- 📱 Mobile application frontend
- ☁ Cloud deployment architecture

The goal is to help farmers, researchers, and agricultural systems detect plant problems early and improve plant survival.

---

# ✨ Features

| Feature | Description |
|--------|-------------|
| 🌿 Disease Detection | Detect cucumber plant disease using YOLOv8 computer vision |
| 🌡 Sensor Monitoring | Collect humidity, temperature, soil nutrient, and light data |
| 📊 Plant Health Analysis | Analyze environmental stress conditions |
| 🧠 AI Recommendations | Generate intelligent recovery suggestions using Llama |
| 📱 Mobile App Support | Connect mobile frontend to backend API |
| ☁ Cloud Ready | Supports Oracle Cloud + Supabase architecture |
| 🔄 Expandable | Supports future retraining and new plant species |

---

# 🏗 System Architecture

```text
Sensors
(DHT22 + Photoresistor + RS485 NPK)
        ↓
ESP32
        ↓
Supabase
(Auth + PostgreSQL + Edge Functions)
        ↓
FastAPI Backend
        ↓
YOLOv8 Vision Model
        ↓
Survival Prediction Engine
        ↓
Llama / Ollama Reasoning Layer
        ↓
Mobile Frontend Application
🛠 Tech Stack
AI / Machine Learning
YOLOv8
Llama
Ollama
Computer Vision
Plant Disease Detection
Backend
FastAPI
Python
Pydantic
Uvicorn
Pillow
NumPy
Frontend
Mobile Application (Frontend Repository)
Database / Cloud
Supabase
PostgreSQL
Oracle Cloud Free Tier
IoT / Hardware
ESP32
DHT22 Sensor
Photoresistor
RS485 NPK Sensor
📂 Project Structure
plant-ai-project/
│
├── artifacts/
│   ├── models/
│   └── registry.json
│
├── backend/
│   ├── config/
│   ├── models/
│   ├── routes/
│   ├── services/
│   ├── uploads/
│   ├── main.py
│   └── requirements.txt
│
├── configs/
│
├── dataset/
│   ├── classification/
│   ├── yolov8/
│   ├── cucumber/
│   └── _imports/
│
├── training/
│   ├── configs/
│   └── scripts/
│
└── README.md
🚀 Installation
Clone Repository
git clone https://github.com/YOUR_USERNAME/Plant-AI-Project.git
cd Plant-AI-Project
Backend Setup
cd backend
pip install -r requirements.txt

Install YOLO training dependencies:

pip install ultralytics
🧪 Training YOLOv8 Model

Train the cucumber disease dataset:

yolo detect train model=yolov8n.pt data=dataset/cucumber/data.yaml epochs=50 imgsz=640 batch=8

After training:

runs/detect/train/weights/best.pt

Copy model:

artifacts/models/cucumber_yolov8.pt
▶ Run Backend

From backend directory:

uvicorn main:app --reload

Open API docs:

http://127.0.0.1:8000/docs
📡 API Endpoints
Endpoint	Method	Purpose
/health	GET	API health check
/predict	POST	Plant image disease detection
/sensor	POST	Sensor data submission
/survival	POST	Plant survival probability
/chat	POST	Llama recommendation / explanation
📱 Frontend (Mobile App)

Mobile frontend is maintained separately.

Frontend repository:

plant-MB

Frontend contributor:

Mohamed Al-Baqir

🧠 AI Workflow
Plant Image Upload
        ↓
Image Preprocessing
        ↓
YOLOv8 Disease Detection
        ↓
Sensor Data Analysis
        ↓
Survival Probability Engine
        ↓
Llama AI Reasoning
        ↓
Final Recommendation Response
🎯 Current MVP Scope

Current MVP includes:

Disease detection
Cucumber dataset support
Backend API
AI inference pipeline
Mobile frontend integration
Sensor architecture planning
Llama recommendation engine
🔮 Future Improvements
Support multiple plant species
Multi-disease classification
Real-time IoT monitoring
Cloud deployment
User authentication
Historical analytics dashboard
Sensor anomaly detection
Retraining pipeline automation
Expanded survival prediction ML models
👥 Team
Backend / AI Architecture

Your Name

Responsibilities:

Backend engineering
FastAPI development
AI orchestration
YOLO integration
Llama integration
System architecture
Frontend / Mobile Application

Mohamed Al-Baqir

Responsibilities:

Mobile frontend development
UI integration
API communication
📖 Project Status

🚧 MVP in active development

Current phase:

Dataset Preparation
→ YOLO Training
→ Backend Integration
→ Frontend Connection
→ Real Testing
💡 Vision

Plant AI Project aims to become a smart agriculture assistant capable of helping farmers detect disease early, improve plant survival, and make data-driven agricultural decisions using AI.
