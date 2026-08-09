# PlantVision Setup Guide

This guide describes how to configure the backend environment for local development and inference.

## 1. Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Review the contents of `.env`. The default configuration uses local storage for image persistence. If you are developing against the Supabase cloud, ensure your `DATABASE_URL` is configured correctly.

## 2. Machine Learning Weights (Multi-Species)

PlantVision uses a species-aware router architecture. Each supported plant species uses its own YOLOv8 model for disease detection.

Because these models are large (several megabytes each), they are **not committed to git**. You must download them from the team's model registry or cloud storage and place them in the correct directories before running the backend.

The required structure inside `artifacts/models/` is:

```
artifacts/models/
├── rose/
│   ├── weights.pt     <-- Place the Rose model here
│   └── data.yaml
├── money_plant/
│   ├── weights.pt     <-- Place the Money Plant model here
│   └── data.yaml
└── cucumber/
    ├── weights.pt     <-- Place the Cucumber model here
    └── data.yaml
```

*Note: If a weights file is missing for a particular species, the backend will gracefully route scans for that species to a multi-provider LLM consensus fallback (or a stub if no API keys are configured).*

## 3. Running the Backend

Install dependencies (if using a virtual environment):

```bash
cd backend
pip install -r requirements.txt
```

Run the server:

```bash
python main.py
```
