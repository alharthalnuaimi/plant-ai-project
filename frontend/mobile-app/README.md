# 🌿 PlantVision AI

**Intelligent Plant Disease Detection & Monitoring Dashboard**

A premium, full-featured botanical lab dashboard built with vanilla HTML/CSS/JS and Node.js. Features AI-powered plant scanning simulation, real-time environmental monitoring, interactive zone management with Leaflet maps, and a Points of Interest (POI) discovery system specialized for Baghdad, Iraq.

---

## ✨ Features

### 🔬 AI Scanner
- Simulated neural engine plant disease detection
- Confidence scoring with animated HUD overlay
- Scan history with pass/warn/critical status

### 📊 Analytics Dashboard
- Real-time scan activity charts
- Detection rate & accuracy metrics
- Species distribution ring charts
- Model performance tracking (precision, recall, F1)
- System metrics with animated ring indicators
- Environmental trend monitoring (temperature, humidity, pH)

### 🗺️ Garden Map
- **Premium Map Tiles** — CartoDB Voyager (street), Dark Matter (dark mode), Esri satellite imagery, OpenTopoMap terrain
- **4 tile layers** with auto theme-sync (dark/light)
- **Geocoded Search** — Debounced search-as-you-type with distance sorting (nearest first)
- **Zone Management** — Full CRUD with map markers, click-to-place, and ESP32 device tracking
- **POI Discovery** — 10 categories of nearby places (Food, Education, Health, Parks, Shops, Fuel, Hotels, ATMs) powered by Overpass API
- **Iraq Specialized** — Geocoding biased to Iraq, default zones in Baghdad

### 💬 AI Chatbot
- Draggable floating chat widget
- Simulated AI responses for plant care queries
- Typing indicators and message history

### 👤 Profile & Settings
- Editable user profile with activity feed
- 30+ configurable settings (scanner, sensors, appearance)
- Light/dark theme toggle with full UI sync

### 📱 Responsive Design
- Desktop sidebar + Mobile bottom navigation
- Optimized for 390px+ mobile viewports
- PWA-ready meta tags

---

## 🚀 Quick Start

```bash
# Clone the repo
git clone https://github.com/mb69i/plant-MB.git
cd plant-MB

# Start the server
node server.js
```

Then open **http://localhost:3000** on your device.

> 💡 Your phone can access it too via the local IP shown in the terminal (e.g., `http://192.168.x.x:3000`)

---

## 🏗️ Architecture

```
vision-ai-plant-app/
├── index.html          # Single-page app with all views
├── style.css           # Full design system (750+ lines)
├── app.js              # Client-side logic (1500+ lines)
├── server.js           # Node.js server with API proxies
├── data/
│   └── appdata.json    # Persistent state (auto-created)
├── scan_preview.png    # Scanner preview image
├── healthy_leaf.png    # Healthy leaf sample
├── diseased_leaf.png   # Diseased leaf sample
└── garden_background.png # Ambient background
```

### Server API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/data` | GET | Fetch app state |
| `/api/data` | POST | Save app state |
| `/api/geocode?q=...` | GET | Proxy to Nominatim geocoding (Iraq-biased) |
| `/api/poi?lat=...&lng=...&cat=...` | GET | Proxy to Overpass API for nearby POIs |

---

## 🎨 Design System

- **Font**: Space Grotesk + IBM Plex Mono
- **Palette**: Sage (#8ca88c), Gunmetal, Gold, Olive, Coral
- **Theme**: Dark (default) + Light mode
- **Style**: Botanical lab / sci-fi HUD aesthetic

---

## 📦 Dependencies

- **Runtime**: Node.js (no npm packages required)
- **Client**: Leaflet.js (CDN), Google Fonts (CDN)
- **APIs**: Nominatim (geocoding), Overpass (POI), CartoDB/Esri (tiles)

---

## 📄 License

MIT © PlantVision AI
