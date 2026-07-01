/* ============================================
   PlantVision AI — Sync Server
   Serves static files + provides a shared data
   API so all devices (PC, phone, tablet) share
   the same zones, notifications, and profile.
   ============================================ */

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');

const PORT = 3000;
const DATA_FILE = path.join(__dirname, 'data', 'appdata.json');
const DATA_DIR = path.join(__dirname, 'data');

// Ensure data directory exists
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });

// Default data structure
const defaultData = {
  theme: 'dark',
  zones: [
    { id:'a', lat:33.3152, lng:44.3661, name:'Alfarabi University', plants:8, status:'Healthy', devices:[{name:'ESP32-A1',ip:'192.168.1.10'}] },
    { id:'b', lat:33.3128, lng:44.3890, name:'Karrada Garden', plants:5, status:'At Risk', devices:[{name:'ESP32-B1',ip:'192.168.1.11'},{name:'ESP32-B2',ip:'192.168.1.12'}] },
    { id:'c', lat:33.3400, lng:44.3650, name:'Mansour Nursery', plants:12, status:'Healthy', devices:[{name:'ESP32-C1',ip:'192.168.1.13'}] },
    { id:'d', lat:33.2950, lng:44.3800, name:'Jadriya Greenhouse', plants:3, status:'Critical', devices:[{name:'ESP32-D1',ip:'192.168.1.14'},{name:'ESP32-D2',ip:'192.168.1.15'},{name:'ESP32-D3',ip:'192.168.1.16'}] }
  ],
  profile: {
    fname: 'Plant',
    lname: 'Researcher',
    email: 'user@plantvision.ai',
    org: 'PlantVision Lab',
    location: 'Baghdad, Iraq'
  },
  notifications: [],
  notifCounter: 100
};

// Load or initialize data
function loadData() {
  try {
    if (fs.existsSync(DATA_FILE)) {
      return JSON.parse(fs.readFileSync(DATA_FILE, 'utf8'));
    }
  } catch (e) {
    console.error('Error reading data file:', e.message);
  }
  return { ...defaultData };
}

function saveData(data) {
  try {
    fs.writeFileSync(DATA_FILE, JSON.stringify(data, null, 2), 'utf8');
  } catch (e) {
    console.error('Error writing data file:', e.message);
  }
}

// Initialize data file if needed
if (!fs.existsSync(DATA_FILE)) saveData(defaultData);

// MIME types for static files
const mimeTypes = {
  '.html': 'text/html',
  '.css': 'text/css',
  '.js': 'application/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};

const server = http.createServer((req, res) => {
  // CORS headers (for local network access)
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    return res.end();
  }

  // === API: GET /api/data — return all shared data ===
  if (req.method === 'GET' && req.url === '/api/data') {
    const data = loadData();
    res.writeHead(200, { 'Content-Type': 'application/json' });
    return res.end(JSON.stringify(data));
  }

  // === API: POST /api/data — update a specific key ===
  // Body: { key: "zones"|"profile"|"notifications"|"notifCounter"|"theme", value: ... }
  if (req.method === 'POST' && req.url === '/api/data') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      try {
        const { key, value } = JSON.parse(body);
        if (!key) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          return res.end(JSON.stringify({ error: 'Missing key' }));
        }
        const data = loadData();
        data[key] = value;
        saveData(data);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ ok: true }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: e.message }));
      }
    });
    return;
  }

  // === API: GET /api/geocode?q=... — proxy geocoding to Nominatim ===
  if (req.method === 'GET' && req.url.startsWith('/api/geocode')) {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const q = url.searchParams.get('q');
    if (!q) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ error: 'Missing q parameter' }));
    }
    const https = require('https');
    const nominatimUrl = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(q)}&limit=8&countrycodes=iq&accept-language=ar,en`;
    https.get(nominatimUrl, { headers: { 'User-Agent': 'PlantVision-App/1.0' } }, (apiRes) => {
      let body = '';
      apiRes.on('data', chunk => body += chunk);
      apiRes.on('end', () => {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(body);
      });
    }).on('error', (e) => {
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: e.message }));
    });
    return;
  }

  // === API: GET /api/poi?lat=...&lng=...&cat=...&r=... — proxy POI search to Overpass ===
  if (req.method === 'GET' && req.url.startsWith('/api/poi')) {
    const url = new URL(req.url, `http://localhost:${PORT}`);
    const lat = url.searchParams.get('lat');
    const lng = url.searchParams.get('lng');
    const cat = url.searchParams.get('cat') || 'food';
    const radius = url.searchParams.get('r') || '1500'; // meters

    if (!lat || !lng) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      return res.end(JSON.stringify({ error: 'Missing lat/lng parameters' }));
    }

    // Map category to Overpass amenity/shop/leisure tags
    const categoryMap = {
      food:       { tags: ['[amenity~"restaurant|cafe|fast_food|bar|pub|bakery"]'] },
      education:  { tags: ['[amenity~"school|university|college|library|kindergarten"]'] },
      health:     { tags: ['[amenity~"hospital|clinic|pharmacy|doctors|dentist"]'] },
      parks:      { tags: ['[leisure~"park|garden|playground|nature_reserve|sports_centre"]'] },
      shops:      { tags: ['[shop]'] },
      fuel:       { tags: ['[amenity~"fuel|charging_station"]'] },
      transport:  { tags: ['[amenity~"bus_station|parking|taxi"]', '[railway~"station|halt"]'] },
      worship:    { tags: ['[amenity~"place_of_worship"]'] },
      hotel:      { tags: ['[tourism~"hotel|motel|hostel|guest_house"]'] },
      atm:        { tags: ['[amenity~"atm|bank"]'] }
    };
    const catDef = categoryMap[cat] || categoryMap.food;

    // Build Overpass QL query — union multiple tag groups
    const parts = catDef.tags.map(tag =>
      `node${tag}(around:${radius},${lat},${lng});way${tag}(around:${radius},${lat},${lng});`
    ).join('');
    const overpassQuery = `[out:json][timeout:25];(${parts});out center body 40;`;
    const https = require('https');
    const postData = `data=${encodeURIComponent(overpassQuery)}`;

    // Try multiple Overpass servers for reliability
    const servers = ['overpass-api.de', 'z.overpass-api.de', 'lz4.overpass-api.de', 'overpass.kumi.systems'];

    function tryOverpass(serverIdx) {
      if (serverIdx >= servers.length) {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        return res.end(JSON.stringify([]));
      }
      const apiReq = https.request({
        hostname: servers[serverIdx],
        path: '/api/interpreter',
        method: 'POST',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
          'User-Agent': 'PlantVision-App/1.0',
          'Content-Length': Buffer.byteLength(postData)
        }
      }, (apiRes) => {
        let body = '';
        apiRes.on('data', chunk => body += chunk);
        apiRes.on('end', () => {
          // If Overpass returned an error, try fallback
          if (apiRes.statusCode !== 200) {
            console.log(`[POI] ${servers[serverIdx]} returned ${apiRes.statusCode}, trying next...`);
            return tryOverpass(serverIdx + 1);
          }
          try {
            const parsed = JSON.parse(body);
            // Simplify the response
            const pois = (parsed.elements || []).map(el => ({
              name: (el.tags && el.tags.name) || (el.tags && el.tags['name:en']) || (el.tags && el.tags['name:ar']) || (el.tags && el.tags.amenity) || (el.tags && el.tags.shop) || 'Unnamed',
              lat: el.lat || (el.center && el.center.lat),
              lon: el.lon || (el.center && el.center.lon),
              type: el.tags && (el.tags.amenity || el.tags.shop || el.tags.leisure || el.tags.tourism || el.tags.railway || cat),
              addr: el.tags && (el.tags['addr:street'] || ''),
              phone: el.tags && (el.tags.phone || ''),
              website: el.tags && (el.tags.website || ''),
              hours: el.tags && (el.tags.opening_hours || '')
            })).filter(p => p.lat && p.lon);
            console.log(`[POI] ${cat}: ${pois.length} results from ${servers[serverIdx]}`);
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(pois));
          } catch (e) {
            console.log(`[POI] Parse error from ${servers[serverIdx]}:`, e.message);
            tryOverpass(serverIdx + 1);
          }
        });
      });
      apiReq.on('error', (e) => {
        console.log(`[POI] Network error for ${servers[serverIdx]}:`, e.message);
        tryOverpass(serverIdx + 1);
      });
      apiReq.write(postData);
      apiReq.end();
    }

    tryOverpass(0);
    return;
  }

  // === Static file serving ===
  let filePath = req.url.split('?')[0];
  if (filePath === '/') filePath = '/index.html';

  const fullPath = path.join(__dirname, filePath);
  const ext = path.extname(fullPath).toLowerCase();

  // Security: prevent directory traversal
  if (!fullPath.startsWith(__dirname)) {
    res.writeHead(403);
    return res.end('Forbidden');
  }

  fs.readFile(fullPath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain' });
      return res.end('Not Found');
    }
    res.writeHead(200, { 'Content-Type': mimeTypes[ext] || 'application/octet-stream' });
    res.end(data);
  });
});

// ── Get local IPs for display ────────────────────────────────────────────────
function getLocalIPs() {
  const interfaces = require('os').networkInterfaces();
  const ips = [];
  for (const name of Object.keys(interfaces)) {
    for (const iface of interfaces[name]) {
      if (iface.family === 'IPv4' && !iface.internal) ips.push(iface.address);
    }
  }
  return ips;
}

// ── HTTP server (port 3000) — works everywhere except camera on phones ────────
const HTTPS_PORT = 3443;
server.listen(PORT, '0.0.0.0', () => {
  const ips = getLocalIPs();
  const localIP = ips[0] || 'localhost';
  console.log(`\n  🌿 PlantVision AI Server Running\n`);
  console.log(`  Local (PC):   http://localhost:${PORT}`);
  console.log(`  Phone (HTTP): http://${localIP}:${PORT}`);
});

// ── HTTPS server (port 3443) — required for camera on phones ─────────────────
const CERT_KEY  = path.join(__dirname, 'cert', 'key.pem');
const CERT_CERT = path.join(__dirname, 'cert', 'cert.pem');

if (fs.existsSync(CERT_KEY) && fs.existsSync(CERT_CERT)) {
  try {
    const tlsOpts = {
      key:  fs.readFileSync(CERT_KEY),
      cert: fs.readFileSync(CERT_CERT),
    };
    const httpsServer = https.createServer(tlsOpts, server.listeners('request')[0]);
    httpsServer.listen(HTTPS_PORT, '0.0.0.0', () => {
      const ips = getLocalIPs();
      const localIP = ips[0] || 'localhost';
      console.log(`  Phone (HTTPS + Camera): https://${localIP}:${HTTPS_PORT}`);
      console.log(`\n  📷 Camera works on HTTPS only.`);
      console.log(`     First visit → tap Advanced → Proceed (accept self-signed cert).`);
      console.log(`\n  Data syncs across all devices ✓\n`);
    });
  } catch (e) {
    console.warn('  ⚠️  HTTPS cert load failed:', e.message);
    console.log(`\n  Data syncs across all devices ✓\n`);
  }
} else {
  console.log(`  ⚠️  No TLS cert found — run: node gen-cert.js  to enable HTTPS + camera on phone.`);
  console.log(`\n  Data syncs across all devices ✓\n`);
}
