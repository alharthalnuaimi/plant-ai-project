/* ============================================
   PlantVision AI — V6 Dashboard Logic
   ============================================ */

// --- Particles (subtle, desaturated) ---
const cv = document.getElementById('particles');
const cx = cv.getContext('2d');
function sz(){ cv.width=innerWidth; cv.height=innerHeight; }
sz(); addEventListener('resize', sz);

const pts = Array.from({length:24}, ()=>({
  x:Math.random()*innerWidth, y:Math.random()*innerHeight,
  r:Math.random()*.7+.3, dx:(Math.random()-.5)*.06, dy:-Math.random()*.1-.02,
  o:Math.random()*.06+.01,
  c:Math.random()>.6 ? '140,168,140' : '150,165,138'
}));

(function draw(){
  cx.clearRect(0,0,cv.width,cv.height);
  pts.forEach(p=>{
    p.x+=p.dx; p.y+=p.dy; p.o-=.00012;
    if(p.o<=0||p.y<-10){p.x=Math.random()*cv.width;p.y=cv.height+10;p.o=Math.random()*.06+.01;}
    cx.beginPath(); cx.arc(p.x,p.y,p.r,0,Math.PI*2);
    cx.fillStyle=`rgba(${p.c},${p.o})`; cx.fill();
  });
  requestAnimationFrame(draw);
})();

// ====== SERVER SYNC LAYER ======
// Syncs data to the server so all devices share the same state
function syncToServer(key, value){
  fetch('/api/data', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({key, value})
  }).catch(()=>{}); // Silently fail if offline
}

async function loadFromServer(){
  try {
    const resp = await fetch('/api/data');
    if(!resp.ok) return null;
    return await resp.json();
  } catch(e){ return null; }
}

// --- HUD simulation ---
setInterval(()=>{
  const c=document.getElementById('s-conf');
  const f=document.getElementById('sys-fps');
  if(c) c.textContent='CONF '+(92+Math.random()*7).toFixed(1)+'%';
  if(f) f.textContent=Math.floor(58+Math.random()*4);
},2200);

// --- Scan (FastAPI POST /predict) ---
const scanModal = document.getElementById('scan-modal');
const resModal  = document.getElementById('res-modal');
const mFill     = document.getElementById('m-fill');
const mLbl      = document.getElementById('m-lbl');
let timer = null;

const scanFileInput = document.createElement('input');
scanFileInput.type = 'file';
scanFileInput.accept = 'image/*';
scanFileInput.capture = 'environment';
scanFileInput.style.display = 'none';
document.body.appendChild(scanFileInput);

function clearScanTimer(){
  if(timer){ clearInterval(timer); timer = null; }
}

function runProgressAnimation(onComplete){
  scanModal.classList.add('active');
  let p = 0;
  mFill.style.width = '0%';
  mLbl.textContent = 'UPLOAD… 0%';
  clearScanTimer();
  timer = setInterval(()=>{
    p += Math.random() * 2.5 + 0.8;
    if(p >= 100){
      p = 100;
      clearScanTimer();
      mFill.style.width = '100%';
      mLbl.textContent = 'INFERENCE…';
      if(onComplete) onComplete();
    } else {
      mFill.style.width = p + '%';
      const ph = p < 30 ? 'UPLOAD…' : p < 60 ? 'VISION…' : 'ANALYZE…';
      mLbl.textContent = `${ph} ${Math.floor(p)}%`;
    }
  }, 80);
}

function showPredictResult(result){
  const disease = result.disease || 'Unknown';
  const confPct = ((result.confidence ?? 0) * 100).toFixed(1) + '%';
  const accepted = result.accepted ? 'Yes' : 'No';
  const inferMs = Math.round(result.inference_ms ?? 0) + ' ms';

  const titleEl = document.getElementById('r-title');
  const speciesEl = document.getElementById('r-species');
  const confEl = document.getElementById('r-conf');
  const hpEl = document.getElementById('r-hp');
  const riskEl = document.getElementById('r-risk');
  const waterEl = document.getElementById('r-water');

  if(titleEl) titleEl.textContent = result.accepted ? 'Analysis Complete' : 'Low Confidence';
  if(speciesEl) speciesEl.textContent = `Cucumber · ${disease}`;
  if(confEl) confEl.textContent = confPct;
  if(hpEl) hpEl.textContent = accepted;
  if(riskEl) riskEl.textContent = inferMs;
  if(waterEl) waterEl.textContent = result.model_name || 'yolov8';

  const confChip = document.getElementById('s-conf');
  if(confChip) confChip.textContent = 'CONF ' + confPct;

  scanModal.classList.remove('active');
  resModal.classList.add('active');
}

function showScanError(message){
  clearScanTimer();
  scanModal.classList.remove('active');
  const titleEl = document.getElementById('r-title');
  const speciesEl = document.getElementById('r-species');
  if(titleEl) titleEl.textContent = 'Scan Failed';
  if(speciesEl) speciesEl.textContent = message;
  resModal.classList.add('active');
}

async function runPlantPredict(file){
  let finishedProgress = false;
  runProgressAnimation(() => { finishedProgress = true; });

  try {
    const result = await predictPlantImage(file);
    const waitDone = () => {
      if(!finishedProgress){
        setTimeout(waitDone, 50);
        return;
      }
      showPredictResult(result);
    };
    waitDone();
  } catch (e) {
    showScanError(e.message || 'Could not reach backend. Is FastAPI running on ' + (window.PLANT_API_BASE || '?') + '?');
  }
}

function triggerScanUpload(){
  scanFileInput.value = '';
  scanFileInput.click();
}

scanFileInput.addEventListener('change', () => {
  const file = scanFileInput.files && scanFileInput.files[0];
  if(file) runPlantPredict(file);
});

document.getElementById('scan-trigger').addEventListener('click', triggerScanUpload);
document.getElementById('act-scan').addEventListener('click', triggerScanUpload);

// Backend health indicator (optional)
(async function checkApiOnLoad(){
  const sysAi = document.getElementById('sys-ai');
  if(!sysAi || typeof checkBackendHealth !== 'function') return;
  const h = await checkBackendHealth();
  if(h.ok){
    sysAi.textContent = 'API OK';
    sysAi.style.color = 'var(--sage)';
  } else {
    sysAi.textContent = 'API offline';
    sysAi.style.color = 'var(--coral)';
  }
})();

document.getElementById('m-cancel').addEventListener('click',()=>{ clearScanTimer(); scanModal.classList.remove('active'); });
document.getElementById('r-dismiss').addEventListener('click',()=> resModal.classList.remove('active'));
document.getElementById('r-save').addEventListener('click', function(){
  this.textContent='✓ Exported'; this.style.opacity='.5';
  setTimeout(()=>{ resModal.classList.remove('active'); this.textContent='Export Report'; this.style.opacity='1'; },800);
});

// --- Page Switching (shared) ---
const pageMap = { n1:'page-home', n2:'page-data', n3:'page-garden', n4:'page-settings' };

function switchPage(targetId){
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  const pg = document.getElementById(targetId);
  if(pg){
    pg.classList.add('active');
    pg.querySelectorAll('.an').forEach(el=>{
      el.style.animation='none';
      el.offsetHeight;
      el.style.animation='';
    });
    // Count-up animations for stat numbers
    if(targetId==='page-home') animateCountUp();
  }
  // Sync sidebar active
  document.querySelectorAll('.sidebar-btn:not(.theme-toggle)').forEach(n=>n.classList.remove('active'));
  const sideBtn = Object.entries(pageMap).find(([k,v])=>v===targetId);
  if(sideBtn){const el=document.getElementById(sideBtn[0]);if(el)el.classList.add('active');}
  // Sync mobile nav active
  document.querySelectorAll('.mn-btn').forEach(b=>{
    b.classList.toggle('active', b.dataset.page===targetId);
  });
}

// Sidebar Nav
document.querySelectorAll('.sidebar-btn:not(.theme-toggle)').forEach(b=>{
  b.addEventListener('click',function(){
    const targetPage = pageMap[this.id];
    if(targetPage) switchPage(targetPage);
  });
});

// Mobile Nav
document.querySelectorAll('.mn-btn').forEach(b=>{
  b.addEventListener('click',function(){
    switchPage(this.dataset.page);
  });
});

// Profile button (topbar)
document.getElementById('btn-user')?.addEventListener('click', () => switchPage('page-profile'));

// --- Count-Up Animation ---
function animateCountUp(){
  document.querySelectorAll('.stat-num').forEach(el=>{
    const target = parseInt(el.textContent);
    if(isNaN(target)) return;
    let current = 0;
    const step = Math.max(1, Math.floor(target/20));
    const interval = setInterval(()=>{
      current += step;
      if(current >= target){ current = target; clearInterval(interval); }
      el.textContent = current;
    }, 30);
  });
}
// Run count-up on first load
setTimeout(animateCountUp, 600);

// --- Day/Night Theme Toggle ---
const themeToggle = document.getElementById('theme-toggle');
const root = document.documentElement;

// Load saved theme (default to dark/night)
const saved = localStorage.getItem('pv-theme');
if(saved === 'light') root.setAttribute('data-theme','light');

function toggleTheme(){
  const isLight = root.getAttribute('data-theme') === 'light';
  if(isLight){
    root.removeAttribute('data-theme');
    localStorage.setItem('pv-theme','dark');
    syncToServer('theme','dark');
    pts.forEach(p => p.c = Math.random()>.6 ? '140,168,140' : '150,165,138');
  } else {
    root.setAttribute('data-theme','light');
    localStorage.setItem('pv-theme','light');
    syncToServer('theme','light');
    pts.forEach(p => p.c = Math.random()>.6 ? '90,122,90' : '107,127,90');
  }
  // Sync map tiles with theme
  if(typeof syncMapTheme === 'function') syncMapTheme();
}

themeToggle.addEventListener('click', toggleTheme);

// If loaded as light, also update particle colors
if(saved === 'light'){
  pts.forEach(p => p.c = Math.random()>.6 ? '90,122,90' : '107,127,90');
}

// ====== ZONE MANAGEMENT (CRUD + LEAFLET MAP) ======
const defaultZones = [
  { id:'a', lat:33.3152, lng:44.3661, name:'Alfarabi University', plants:8, status:'Healthy', devices:[{name:'ESP32-A1',ip:'192.168.1.10'}] },
  { id:'b', lat:33.3128, lng:44.3890, name:'Karrada Garden', plants:5, status:'At Risk', devices:[{name:'ESP32-B1',ip:'192.168.1.11'},{name:'ESP32-B2',ip:'192.168.1.12'}] },
  { id:'c', lat:33.3400, lng:44.3650, name:'Mansour Nursery', plants:12, status:'Healthy', devices:[{name:'ESP32-C1',ip:'192.168.1.13'}] },
  { id:'d', lat:33.2950, lng:44.3800, name:'Jadriya Greenhouse', plants:3, status:'Critical', devices:[{name:'ESP32-D1',ip:'192.168.1.14'},{name:'ESP32-D2',ip:'192.168.1.15'},{name:'ESP32-D3',ip:'192.168.1.16'}] }
];

let zones = JSON.parse(localStorage.getItem('pv-zones')) || defaultZones;
let gardenMap = null;
let mapMarkers = {};
let editingZone = null;
let pendingLatLng = null;
let mapClickMode = false;

function statusColor(s){
  if(s==='Healthy') return '#8ca88c';
  if(s==='At Risk') return '#c0a06a';
  return '#b07070';
}
function statusClass(s){
  if(s==='Healthy') return 'ok';
  if(s==='At Risk') return 'warn';
  return 'crit';
}

function saveZones(){ localStorage.setItem('pv-zones', JSON.stringify(zones)); syncToServer('zones', zones); }

function renderZoneChips(){
  const list = document.getElementById('zone-list');
  const counter = document.getElementById('zone-counter');
  if(!list) return;
  list.innerHTML = '';
  counter.textContent = zones.length + ' Zone' + (zones.length!==1?'s':'') + ' Active';
  zones.forEach(z=>{
    const cls = statusClass(z.status);
    const chip = document.createElement('div');
    chip.className = 'zone-chip';
    chip.innerHTML = `<span class="zone-chip-dot zcd-${cls}"></span>${z.id.toUpperCase()} — ${z.name}<span class="zone-chip-count mono">${z.plants}</span><div class="zone-chip-actions"><button class="zone-chip-btn zb-edit" data-id="${z.id}" title="Edit">✎</button><button class="zone-chip-btn zb-del" data-id="${z.id}" title="Delete">✕</button></div>`;
    // Click chip → fly to location
    chip.addEventListener('click',(e)=>{
      if(e.target.closest('.zone-chip-btn')) return;
      if(gardenMap) gardenMap.flyTo([z.lat,z.lng],18,{duration:0.8});
    });
    list.appendChild(chip);
  });
  // Bind edit/delete buttons
  list.querySelectorAll('.zb-edit').forEach(b=>b.addEventListener('click',()=>openZoneModal(b.dataset.id)));
  list.querySelectorAll('.zb-del').forEach(b=>b.addEventListener('click',()=>deleteZone(b.dataset.id)));
}

function renderMapMarkers(){
  if(!gardenMap) return;
  Object.values(mapMarkers).forEach(m=>gardenMap.removeLayer(m));
  mapMarkers = {};
  zones.forEach(z=>{
    const c = statusColor(z.status);
    const marker = L.circleMarker([z.lat,z.lng],{
      radius:14, fillColor:c, fillOpacity:.7, color:c, weight:2, opacity:.9
    }).addTo(gardenMap);
    marker.bindPopup(`<div style="font-family:var(--font);text-align:center"><b style="font-size:14px">Zone ${z.id.toUpperCase()}</b><br><span style="font-size:12px">${z.name}</span><br><span style="font-size:11px;color:#888">${z.plants} plants · ${z.status}</span></div>`);
    mapMarkers[z.id] = marker;
  });
}

// --- Zone Modal ---
const zoneModal = document.getElementById('zone-modal');
const zmTitle = document.getElementById('zm-title');
const zmDesc = document.getElementById('zm-desc');
const zmName = document.getElementById('zm-name');
const zmStatus = document.getElementById('zm-status');
const zmPlants = document.getElementById('zm-plants');
const zmCoords = document.getElementById('zm-coords');
const zmCoordsText = document.getElementById('zm-coords-text');
const zmSave = document.getElementById('zm-save');
const zmCancel = document.getElementById('zm-cancel');
const zmDelete = document.getElementById('zm-delete');

function openZoneModal(zoneId){
  editingZone = zoneId ? zones.find(z=>z.id===zoneId) : null;
  pendingLatLng = null;
  if(editingZone){
    zmTitle.textContent = 'Edit Zone ' + editingZone.id.toUpperCase();
    zmDesc.textContent = 'Modify zone details or click map to move';
    zmName.value = editingZone.name;
    zmStatus.value = editingZone.status;
    zmPlants.value = editingZone.plants;
    zmCoordsText.textContent = editingZone.lat.toFixed(4)+', '+editingZone.lng.toFixed(4);
    zmCoords.classList.add('has-coords');
    zmDelete.style.display = 'block';
    zmSave.textContent = 'Update Zone';
    pendingLatLng = {lat:editingZone.lat,lng:editingZone.lng};
    renderModalDevices(editingZone.devices||[]);
  } else {
    zmTitle.textContent = 'Add New Zone';
    zmDesc.textContent = 'Fill in details, then click map to set location';
    zmName.value = '';
    zmStatus.value = 'Healthy';
    zmPlants.value = 1;
    zmCoordsText.textContent = 'Click map to set location';
    zmCoords.classList.remove('has-coords');
    zmDelete.style.display = 'none';
    zmSave.textContent = 'Save Zone';
    renderModalDevices([{name:'',ip:''}]);
  }
  mapClickMode = true;
  zoneModal.classList.add('active');
  // Reset delete button state
  zmDelete.dataset.confirm = '';
  zmDelete.textContent = 'Delete Zone';
  zmDelete.style.background = '';
  clearTimeout(zmDelete._resetTimer);
}

function closeZoneModal(){
  zoneModal.classList.remove('active');
  mapClickMode = false;
  editingZone = null;
  pendingLatLng = null;
  // Reset delete button state
  zmDelete.dataset.confirm = '';
  zmDelete.textContent = 'Delete Zone';
  zmDelete.style.background = '';
}

zmCancel.addEventListener('click', closeZoneModal);

zmSave.addEventListener('click', ()=>{
  const name = zmName.value.trim();
  if(!name){ zmName.style.borderColor='var(--coral)'; return; }
  if(!pendingLatLng){ zmCoordsText.textContent='\u26a0 Click map first!'; return; }
  const devices = getModalDevices();
  if(editingZone){
    editingZone.name = name;
    editingZone.status = zmStatus.value;
    editingZone.plants = parseInt(zmPlants.value)||0;
    editingZone.lat = pendingLatLng.lat;
    editingZone.lng = pendingLatLng.lng;
    editingZone.devices = devices;
  } else {
    const nextId = String.fromCharCode(97 + zones.length); // a,b,c...
    zones.push({ id:nextId, lat:pendingLatLng.lat, lng:pendingLatLng.lng, name, plants:parseInt(zmPlants.value)||0, status:zmStatus.value, devices });
  }
  saveZones();
  renderZoneChips();
  renderMapMarkers();
  renderDevicePanel();
  closeZoneModal();
});

zmDelete.addEventListener('click', ()=>{
  if(editingZone){
    // Two-click inline confirm for modal delete
    if(zmDelete.dataset.confirm === 'true'){
      executeDeleteZone(editingZone.id);
      closeZoneModal();
    } else {
      zmDelete.dataset.confirm = 'true';
      zmDelete.textContent = '⚠ Confirm Delete?';
      zmDelete.style.background = 'var(--coral-dim)';
      zmDelete._resetTimer = setTimeout(()=>{
        zmDelete.dataset.confirm = '';
        zmDelete.textContent = 'Delete Zone';
        zmDelete.style.background = '';
      }, 3000);
    }
  }
});

// Actual delete execution (no confirm dialog)
function executeDeleteZone(id){
  zones = zones.filter(z=>z.id!==id);
  if(mapMarkers[id]){
    if(gardenMap) gardenMap.removeLayer(mapMarkers[id]);
    delete mapMarkers[id];
  }
  saveZones();
  renderZoneChips();
  renderMapMarkers();
  renderDevicePanel();
}

// deleteZone from chip buttons — inline 2-click confirm
function deleteZone(id){
  // Find the delete button for this zone
  const btn = document.querySelector(`.zb-del[data-id="${id}"]`);
  if(!btn) return;
  if(btn.dataset.confirm === 'true'){
    // Second click: actually delete
    executeDeleteZone(id);
  } else {
    // First click: show confirm state
    btn.dataset.confirm = 'true';
    btn.textContent = '✓';
    btn.title = 'Click again to confirm';
    btn.style.background = 'var(--coral-dim)';
    btn.style.color = 'var(--coral)';
    btn.style.width = 'auto';
    btn.style.padding = '2px 6px';
    // Auto-reset after 3 seconds
    clearTimeout(btn._resetTimer);
    btn._resetTimer = setTimeout(()=>{
      btn.dataset.confirm = '';
      btn.textContent = '✕';
      btn.title = 'Delete';
      btn.style.background = '';
      btn.style.color = '';
      btn.style.width = '';
      btn.style.padding = '';
    }, 3000);
  }
}

document.getElementById('zone-add-btn').addEventListener('click', ()=>openZoneModal());

// --- Leaflet Map Init ---
// Premium tile layers (free, no API key required)
const tileLayers = {
  street: {
    name: 'Street',
    url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
    opts: { attribution:'© <a href="https://carto.com/">CARTO</a> © <a href="https://osm.org/">OSM</a>', maxZoom:20, subdomains:'abcd' }
  },
  dark: {
    name: 'Dark',
    url: 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
    opts: { attribution:'© <a href="https://carto.com/">CARTO</a> © <a href="https://osm.org/">OSM</a>', maxZoom:20, subdomains:'abcd' }
  },
  satellite: {
    name: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    opts: { attribution:'© Esri, Maxar, Earthstar Geographics', maxZoom:19 }
  },
  terrain: {
    name: 'Terrain',
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    opts: { attribution:'© <a href="https://opentopomap.org/">OpenTopoMap</a> © OSM', maxZoom:17 }
  }
};
let activeLayer = null;
let layerControl = null;

function initMap(){
  if(gardenMap) return;
  const mapEl = document.getElementById('leaflet-map');
  if(!mapEl || typeof L === 'undefined') return;
  gardenMap = L.map(mapEl,{zoomControl:false}).setView([33.315,44.366],14);
  L.control.zoom({position:'topright'}).addTo(gardenMap);

  // Choose default based on current theme
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const defaultKey = isDark ? 'dark' : 'street';

  // Create all layers
  const leafletLayers = {};
  Object.entries(tileLayers).forEach(([key, cfg]) => {
    leafletLayers[cfg.name] = L.tileLayer(cfg.url, cfg.opts);
  });

  // Add default layer
  activeLayer = leafletLayers[tileLayers[defaultKey].name];
  activeLayer.addTo(gardenMap);

  // Add layer control (top-left)
  layerControl = L.control.layers(leafletLayers, null, {
    position: 'topleft',
    collapsed: true
  }).addTo(gardenMap);

  // Track active layer for theme sync
  gardenMap.on('baselayerchange', (e) => {
    activeLayer = e.layer;
  });

  // Map click → set zone coordinates OR prompt to add zone
  gardenMap.on('click',(e)=>{
    if(mapClickMode){
      // Zone modal is open — set location for the zone being edited/added
      pendingLatLng = {lat:e.latlng.lat, lng:e.latlng.lng};
      zmCoordsText.textContent = e.latlng.lat.toFixed(4)+', '+e.latlng.lng.toFixed(4);
      zmCoords.classList.add('has-coords');
    } else {
      // No modal open — show "Add zone here?" popup
      const popup = L.popup()
        .setLatLng(e.latlng)
        .setContent(`<div style="font-family:var(--font);text-align:center;padding:4px">
          <div style="font-size:12px;font-weight:600;margin-bottom:6px;color:#333">Add a zone here?</div>
          <div style="font-size:10px;color:#777;margin-bottom:8px">${e.latlng.lat.toFixed(4)}, ${e.latlng.lng.toFixed(4)}</div>
          <button onclick="window._addZoneAtClick(${e.latlng.lat},${e.latlng.lng})" style="padding:6px 16px;border:none;border-radius:6px;background:#5a7a5a;color:#fff;font-size:11px;font-weight:600;cursor:pointer;font-family:inherit">+ Add Zone</button>
        </div>`)
        .openOn(gardenMap);
    }
  });

  // Global helper for popup button
  window._addZoneAtClick = function(lat, lng){
    gardenMap.closePopup();
    openZoneModal();
    pendingLatLng = {lat, lng};
    zmCoordsText.textContent = lat.toFixed(4)+', '+lng.toFixed(4);
    zmCoords.classList.add('has-coords');
  };

  renderMapMarkers();
}

// Sync map tiles with theme toggle
function syncMapTheme(){
  if(!gardenMap || !layerControl) return;
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const targetKey = isDark ? 'dark' : 'street';
  const targetLayer = L.tileLayer(tileLayers[targetKey].url, tileLayers[targetKey].opts);
  if(activeLayer) gardenMap.removeLayer(activeLayer);
  targetLayer.addTo(gardenMap);
  activeLayer = targetLayer;
}

// --- Map Search (Nominatim Geocoding via server proxy) ---
let _searchInitDone = false;
function initMapSearch(){
  if(_searchInitDone) return;
  const searchInput = document.getElementById('map-search');
  const searchBtn = document.getElementById('map-search-btn');
  if(!searchInput || !searchBtn) return;
  _searchInitDone = true;

  // Create results dropdown
  let resultsDiv = document.querySelector('.map-search-results');
  if(!resultsDiv){
    resultsDiv = document.createElement('div');
    resultsDiv.className = 'map-search-results';
    searchInput.parentElement.appendChild(resultsDiv);
  }

  // Haversine distance (km) between two lat/lng points
  function haversine(lat1, lon1, lat2, lon2){
    const R = 6371;
    const dLat = (lat2-lat1)*Math.PI/180;
    const dLon = (lon2-lon1)*Math.PI/180;
    const a = Math.sin(dLat/2)*Math.sin(dLat/2) +
              Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*
              Math.sin(dLon/2)*Math.sin(dLon/2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  }

  // Format distance for display
  function fmtDist(km){
    if(km < 1) return Math.round(km*1000) + ' m';
    if(km < 100) return km.toFixed(1) + ' km';
    return Math.round(km).toLocaleString() + ' km';
  }

  // Debounce timer for search-as-you-type
  let _searchTimer = null;

  async function doSearch(){
    const q = searchInput.value.trim();
    if(!q){ resultsDiv.classList.remove('active'); return; }
    searchBtn.innerHTML = '<span class="map-search-spin">⟳</span>';
    searchBtn.disabled = true;
    if(gardenMap) gardenMap.closePopup();
    resultsDiv.innerHTML = '<div class="map-sr-loading"><span class="map-sr-dots">Searching</span></div>';
    resultsDiv.classList.add('active');
    try{
      const resp = await fetch('/api/geocode?q=' + encodeURIComponent(q));
      if(!resp.ok) throw new Error('Server returned ' + resp.status);
      const data = await resp.json();
      resultsDiv.innerHTML = '';
      if(!Array.isArray(data) || data.length === 0){
        resultsDiv.innerHTML = '<div class="map-sr-item map-sr-empty"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>No results for "' + q + '"</div>';
        resultsDiv.classList.add('active');
        return;
      }

      // Get map center for distance calculation
      const center = gardenMap ? gardenMap.getCenter() : {lat:33.315, lng:44.366};

      // Add distance to each item and sort nearest first
      const enriched = data.map(item => {
        const lat = parseFloat(item.lat);
        const lon = parseFloat(item.lon);
        const dist = haversine(center.lat, center.lng, lat, lon);
        return { ...item, lat, lon, dist };
      });
      enriched.sort((a,b) => a.dist - b.dist);

      // Deduplicate by display_name (Nominatim sometimes returns duplicates)
      const seen = new Set();
      const unique = enriched.filter(item => {
        const key = item.display_name;
        if(seen.has(key)) return false;
        seen.add(key);
        return true;
      });

      unique.forEach((item, idx) => {
        const div = document.createElement('div');
        div.className = 'map-sr-item';
        // Parse display name into primary + secondary
        const parts = item.display_name.split(',');
        const primary = parts[0].trim();
        const secondary = parts.slice(1, 3).map(s=>s.trim()).join(', ');
        div.innerHTML =
          '<div class="map-sr-main">' +
            '<span class="map-sr-name">' + primary + '</span>' +
            (secondary ? '<span class="map-sr-sub">' + secondary + '</span>' : '') +
          '</div>' +
          '<span class="map-sr-dist">' + fmtDist(item.dist) + '</span>';

        div.addEventListener('click',()=>{
          if(gardenMap){
            // Smart zoom: closer = more zoom
            const zoom = item.dist < 1 ? 17 : item.dist < 10 ? 15 : item.dist < 100 ? 12 : item.dist < 1000 ? 8 : 5;
            gardenMap.flyTo([item.lat, item.lon], zoom, {duration:1.2});
            if(window._searchMarker) gardenMap.removeLayer(window._searchMarker);
            window._searchMarker = L.marker([item.lat, item.lon]).addTo(gardenMap)
              .bindPopup('<div style="font-family:var(--font);text-align:center"><b>' + primary + '</b><br><span style="font-size:10px;color:#888">' + fmtDist(item.dist) + ' away</span></div>').openPopup();
          }
          searchInput.value = primary;
          resultsDiv.classList.remove('active');
        });
        resultsDiv.appendChild(div);
      });
      resultsDiv.classList.add('active');
    } catch(err){
      console.warn('Search failed:', err);
      resultsDiv.innerHTML = '<div class="map-sr-item map-sr-error"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>Search failed — try again</div>';
      resultsDiv.classList.add('active');
    } finally {
      searchBtn.textContent = 'Go';
      searchBtn.disabled = false;
    }
  }

  searchBtn.addEventListener('click', doSearch);
  searchInput.addEventListener('keydown', e=>{ if(e.key==='Enter'){ clearTimeout(_searchTimer); doSearch(); }});

  // Debounced search-as-you-type (300ms delay)
  searchInput.addEventListener('input', ()=>{
    clearTimeout(_searchTimer);
    const q = searchInput.value.trim();
    if(q.length >= 3){
      _searchTimer = setTimeout(doSearch, 300);
    } else if(q.length === 0){
      resultsDiv.classList.remove('active');
    }
  });

  // Close dropdown on click outside
  document.addEventListener('click', e=>{
    if(!e.target.closest('.map-search-wrap')) resultsDiv.classList.remove('active');
  });
}

// ====== POI (Points of Interest) System ======
let poiMarkers = [];
let activePOICat = null;

const poiIcons = {
  food: '🍽️', education: '🎓', health: '🏥', parks: '🌳',
  shops: '🛒', fuel: '⛽', hotel: '🏨', atm: '🏦',
  transport: '🚌', worship: '🕌'
};
const poiColors = {
  food: '#e67e22', education: '#3498db', health: '#e74c3c', parks: '#27ae60',
  shops: '#9b59b6', fuel: '#f39c12', hotel: '#1abc9c', atm: '#2c3e50',
  transport: '#7f8c8d', worship: '#8e44ad'
};

function clearPOIMarkers(){
  poiMarkers.forEach(m => { if(gardenMap) gardenMap.removeLayer(m); });
  poiMarkers = [];
  const status = document.getElementById('poi-status');
  if(status) status.innerHTML = '';
  const clearBtn = document.getElementById('poi-clear');
  if(clearBtn) clearBtn.style.display = 'none';
  document.querySelectorAll('.poi-btn').forEach(b => b.classList.remove('active'));
  activePOICat = null;
}

async function loadPOI(cat){
  if(!gardenMap) return;
  const status = document.getElementById('poi-status');
  const clearBtn = document.getElementById('poi-clear');

  // Toggle off if same category
  if(activePOICat === cat){ clearPOIMarkers(); return; }

  // Clear previous
  clearPOIMarkers();
  activePOICat = cat;

  // Highlight active button
  document.querySelectorAll('.poi-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.cat === cat);
  });

  const center = gardenMap.getCenter();
  if(status) status.innerHTML = '<span style="color:var(--sage)">⟳</span> Finding nearby ' + cat + '...';

  try {
    const resp = await fetch(`/api/poi?lat=${center.lat}&lng=${center.lng}&cat=${cat}&r=2500`);
    if(!resp.ok) throw new Error('Server error');
    const pois = await resp.json();

    if(!Array.isArray(pois) || pois.length === 0){
      if(status) status.innerHTML = 'No ' + cat + ' found nearby. Try panning the map.';
      return;
    }

    const color = poiColors[cat] || '#8ca88c';
    const icon = poiIcons[cat] || '📍';

    pois.forEach(poi => {
      if(!poi.lat || !poi.lon) return;
      const marker = L.circleMarker([poi.lat, poi.lon], {
        radius: 8,
        fillColor: color,
        fillOpacity: 0.85,
        color: '#fff',
        weight: 2,
        opacity: 0.9
      }).addTo(gardenMap);

      // Build popup content
      let popupHTML = `<div style="font-family:var(--font);min-width:140px">`;
      popupHTML += `<div style="font-size:13px;font-weight:700;margin-bottom:4px">${icon} ${poi.name}</div>`;
      popupHTML += `<div style="font-size:10px;color:#888;margin-bottom:2px">${poi.type || cat}</div>`;
      if(poi.addr) popupHTML += `<div style="font-size:10px;color:#666">📍 ${poi.addr}</div>`;
      if(poi.phone) popupHTML += `<div style="font-size:10px;color:#666">📞 ${poi.phone}</div>`;
      if(poi.hours) popupHTML += `<div style="font-size:10px;color:#666">🕐 ${poi.hours}</div>`;
      popupHTML += `</div>`;

      marker.bindPopup(popupHTML);
      poiMarkers.push(marker);
    });

    if(status) status.innerHTML = `<span class="poi-count">${pois.length}</span> ${cat} places found within 2.5 km`;
    if(clearBtn) clearBtn.style.display = '';

  } catch(err){
    console.warn('POI load failed:', err);
    if(status) status.innerHTML = '<span style="color:var(--coral)">Failed to load POIs — try again</span>';
  }
}

function initPOI(){
  document.querySelectorAll('.poi-btn:not(.poi-btn-clear)').forEach(btn => {
    btn.addEventListener('click', () => loadPOI(btn.dataset.cat));
  });
  const clearBtn = document.getElementById('poi-clear');
  if(clearBtn) clearBtn.addEventListener('click', clearPOIMarkers);
}

// Observer to init map on garden page
const mapObs = new MutationObserver(()=>{
  const pg = document.getElementById('page-garden');
  if(pg && pg.classList.contains('active')){
    setTimeout(()=>{ initMap(); if(gardenMap) gardenMap.invalidateSize(); initMapSearch(); initPOI(); },100);
  }
});
mapObs.observe(document.querySelector('.content'),{subtree:true,attributes:true,attributeFilter:['class']});

// Render zone chips on load
renderZoneChips();

// ====== AI CHATBOT ======
const chatWidget = document.getElementById('chat-widget');
const chatFab = document.getElementById('chat-fab');
const chatBody = document.getElementById('chat-body');
const chatInput = document.getElementById('chat-input');
const chatSend = document.getElementById('chat-send');

// Draggable chat widget + click to toggle
let chatDragging = false;
let chatStartX, chatStartY, chatOrigLeft, chatOrigTop;
let chatMoved = false;

function getChatPos(){
  const r = chatWidget.getBoundingClientRect();
  return {left: r.left, top: r.top};
}

function onChatDragStart(clientX, clientY){
  chatDragging = true;
  chatMoved = false;
  chatWidget.classList.add('dragging');
  const pos = getChatPos();
  chatStartX = clientX;
  chatStartY = clientY;
  // Switch from bottom/right to top/left for free positioning
  chatWidget.style.left = pos.left + 'px';
  chatWidget.style.top = pos.top + 'px';
  chatWidget.style.right = 'auto';
  chatWidget.style.bottom = 'auto';
  chatOrigLeft = pos.left;
  chatOrigTop = pos.top;
}

function onChatDragMove(clientX, clientY){
  if(!chatDragging) return;
  const dx = clientX - chatStartX;
  const dy = clientY - chatStartY;
  if(Math.abs(dx)>4 || Math.abs(dy)>4) chatMoved = true;
  let newLeft = chatOrigLeft + dx;
  let newTop = chatOrigTop + dy;
  // Clamp to viewport
  newLeft = Math.max(0, Math.min(window.innerWidth - 60, newLeft));
  newTop = Math.max(0, Math.min(window.innerHeight - 60, newTop));
  chatWidget.style.left = newLeft + 'px';
  chatWidget.style.top = newTop + 'px';
}

function onChatDragEnd(){
  if(!chatDragging) return;
  chatDragging = false;
  chatWidget.classList.remove('dragging');
  // Save position
  localStorage.setItem('pv-chat-pos', JSON.stringify({
    left: chatWidget.style.left,
    top: chatWidget.style.top
  }));
}

// Mouse events
chatFab.addEventListener('mousedown', e=>{
  e.preventDefault();
  onChatDragStart(e.clientX, e.clientY);
});
document.addEventListener('mousemove', e=>{ onChatDragMove(e.clientX, e.clientY); });
document.addEventListener('mouseup', ()=>{
  if(chatDragging){
    onChatDragEnd();
    if(!chatMoved) chatWidget.classList.toggle('open');
  }
});

// Touch events
chatFab.addEventListener('touchstart', e=>{
  const t = e.touches[0];
  onChatDragStart(t.clientX, t.clientY);
}, {passive:true});
document.addEventListener('touchmove', e=>{
  if(!chatDragging) return;
  const t = e.touches[0];
  onChatDragMove(t.clientX, t.clientY);
}, {passive:false});
document.addEventListener('touchend', ()=>{
  if(chatDragging){
    onChatDragEnd();
    if(!chatMoved) chatWidget.classList.toggle('open');
  }
});

// Click fallback (for non-drag clicks)
chatFab.addEventListener('click', e=>{
  if(!chatMoved && !chatDragging){
    chatWidget.classList.toggle('open');
  }
  chatMoved = false;
});

// Restore saved position
const savedChatPos = JSON.parse(localStorage.getItem('pv-chat-pos') || 'null');
if(savedChatPos){
  chatWidget.style.left = savedChatPos.left;
  chatWidget.style.top = savedChatPos.top;
  chatWidget.style.right = 'auto';
  chatWidget.style.bottom = 'auto';
}

const botResponses = [
  {k:['hello','hi','hey'], r:"Hello! How can I help with your plants today? 🌱"},
  {k:['leaf spot','spots','brown spot'], r:"Leaf spots are often caused by fungal infections. Remove affected leaves, improve air circulation, and apply a copper-based fungicide. Avoid overhead watering."},
  {k:['yellow','yellowing'], r:"Yellowing leaves can indicate overwatering, nutrient deficiency (especially nitrogen), or insufficient light. Check soil moisture first — let the top inch dry between waterings."},
  {k:['water','watering','how often'], r:"Most indoor plants prefer watering when the top 1-2 inches of soil are dry. Your capacitive soil sensor reads "+document.getElementById('s-soil')?.textContent+". Below 30% usually means it's time to water."},
  {k:['ph','acid','alkaline'], r:"Most plants thrive in pH 6.0–7.0. Your DFRobot sensor reads pH "+document.getElementById('s-ph')?.textContent+". If too acidic, add lime; if too alkaline, add sulfur or peat moss."},
  {k:['temperature','temp','cold','hot'], r:"Your DHT22 reads "+document.getElementById('s-airtemp')?.textContent+" air and DS18B20 reads "+document.getElementById('s-soiltemp')?.textContent+" soil. Most houseplants prefer 18–26°C. Avoid sudden temperature changes."},
  {k:['humidity','mist','dry'], r:"Current humidity is "+document.getElementById('s-humidity')?.textContent+". Most tropicals prefer 50-70%. Consider a humidifier or pebble tray if below 40%."},
  {k:['light','sun','shade','lux'], r:"BH1750 reads "+document.getElementById('s-lux')?.textContent+" lux. Low light plants need 200-500 lux, medium 500-1000, and high light plants need 1000+ lux."},
  {k:['ec','fertilizer','nutrient','feed'], r:"EC sensor reads "+document.getElementById('s-ec')?.textContent+" mS/cm. Optimal range for most plants is 1.2–2.0 mS/cm. Below 1.0 may need fertilizing."},
  {k:['scan','disease','diagnose'], r:"Use the scanner on the Home tab to diagnose plant diseases. Point the camera at a leaf and click the scan button. The AI model will identify issues with 90%+ accuracy."},
  {k:['monstera','deliciosa'], r:"Monstera deliciosa thrives in bright indirect light, moderate watering, and 60-80% humidity. Watch for root rot — ensure drainage holes and well-draining soil."},
  {k:['zone','garden','map'], r:"You have 4 active zones. Zone B (Herb Garden) shows 'At Risk' status — the basil may need more water. Zone D (Greenhouse) has a critical fungus alert. Check the Garden Map for details."},
];

function getBotReply(msg){
  const lower = msg.toLowerCase();
  for(const b of botResponses){
    if(b.k.some(k=> lower.includes(k))) return b.r;
  }
  return "I can help with plant care, disease identification, sensor readings, and garden management. Try asking about watering, pH levels, light requirements, or specific plant species! 🌿";
}

function addMsg(text, isUser){
  const div = document.createElement('div');
  div.className = `chat-msg ${isUser ? 'chat-msg-user' : 'chat-msg-bot'}`;
  const now = new Date();
  const time = now.getHours().toString().padStart(2,'0')+':'+now.getMinutes().toString().padStart(2,'0');
  div.innerHTML = `<div class="chat-bubble">${text}</div><span class="chat-time mono">${time}</span>`;
  chatBody.appendChild(div);
  chatBody.scrollTop = chatBody.scrollHeight;
}

function showTyping(){
  const div = document.createElement('div');
  div.className = 'chat-msg chat-msg-bot';
  div.id = 'chat-typing';
  div.innerHTML = '<div class="chat-bubble"><div class="chat-typing"><span></span><span></span><span></span></div></div>';
  chatBody.appendChild(div);
  chatBody.scrollTop = chatBody.scrollHeight;
}

function sendMsg(){
  const text = chatInput.value.trim();
  if(!text) return;
  addMsg(text, true);
  chatInput.value = '';
  showTyping();
  setTimeout(()=>{
    const typing = document.getElementById('chat-typing');
    if(typing) typing.remove();
    addMsg(getBotReply(text), false);
  }, 800 + Math.random()*600);
}

chatSend.addEventListener('click', sendMsg);
chatInput.addEventListener('keydown', e=>{ if(e.key==='Enter') sendMsg(); });

// ====== DEVICE MODAL HELPERS ======
const zmDeviceList = document.getElementById('zm-device-list');
const zmAddDevice = document.getElementById('zm-add-device');

function renderModalDevices(devices){
  zmDeviceList.innerHTML = '';
  devices.forEach((d,i)=>{
    const row = document.createElement('div');
    row.className = 'zm-device-row';
    row.innerHTML = `<input type="text" class="zm-input zm-dev-name" placeholder="Device name" value="${d.name||''}">`+
      `<input type="text" class="zm-input zm-device-ip" placeholder="IP address" value="${d.ip||''}">`+
      `<button class="zm-device-rm" type="button" title="Remove">\u2715</button>`;
    row.querySelector('.zm-device-rm').addEventListener('click',()=>{ row.remove(); });
    zmDeviceList.appendChild(row);
  });
}

function getModalDevices(){
  return Array.from(zmDeviceList.querySelectorAll('.zm-device-row')).map(r=>({
    name: r.querySelector('.zm-dev-name').value.trim(),
    ip: r.querySelector('.zm-device-ip').value.trim()
  })).filter(d=>d.name||d.ip);
}

zmAddDevice.addEventListener('click',()=>{
  renderModalDevices([...getModalDevices(),{name:'',ip:''}]);
});

// ====== DEVICE PANEL (SIDEBAR) ======
// viewMode: 'all' | 'zone:X' | 'dev:zoneId_index'
let viewMode = 'all';
let deviceSensorData = {};

function getAllDevices(){
  const all = [];
  zones.forEach(z=>{
    (z.devices||[]).forEach((d,i)=>{
      all.push({ ...d, uid: z.id+'_'+i, zoneId: z.id, zoneName: z.name });
    });
  });
  return all;
}

function renderDevicePanel(){
  const panel = document.getElementById('device-panel');
  const counter = document.getElementById('device-counter');
  if(!panel) return;
  const allDevs = getAllDevices();
  counter.textContent = allDevs.length + ' Device'+(allDevs.length!==1?'s':'');
  panel.innerHTML = '';

  if(allDevs.length === 0){
    panel.innerHTML = '<div class="dev-no-devices">No devices configured. Edit a zone to add ESP32 devices.</div>';
    return;
  }

  // --- Summary bar (averaged values) ---
  const sumDiv = document.createElement('div');
  sumDiv.className = 'dev-summary';
  const avg = calcAverages();
  sumDiv.innerHTML =
    `<div class="dev-sum-item"><span class="dev-sum-val">${avg.temp}</span><span class="dev-sum-lbl">Avg °C</span></div>`+
    `<div class="dev-sum-item"><span class="dev-sum-val">${avg.hum}</span><span class="dev-sum-lbl">Avg Hum</span></div>`+
    `<div class="dev-sum-item"><span class="dev-sum-val">${avg.ph}</span><span class="dev-sum-lbl">Avg pH</span></div>`+
    `<div class="dev-sum-item"><span class="dev-sum-val">${avg.soil}</span><span class="dev-sum-lbl">Avg Soil</span></div>`;
  panel.appendChild(sumDiv);

  // --- View mode selector ---
  const selRow = document.createElement('div');
  selRow.className = 'dev-selector';
  let opts = `<option value="all"${viewMode==='all'?' selected':''}>All Devices (${allDevs.length})</option>`;
  // Zone options
  zones.forEach(z=>{
    const devCount = (z.devices||[]).length;
    if(devCount > 0){
      const sel = viewMode===('zone:'+z.id)?' selected':'';
      opts += `<option value="zone:${z.id}"${sel}>Zone ${z.id.toUpperCase()} — ${z.name} (${devCount})</option>`;
    }
  });
  // Individual device options
  allDevs.forEach(d=>{
    const sel = viewMode===('dev:'+d.uid)?' selected':'';
    opts += `<option value="dev:${d.uid}"${sel}>${d.name||'Unnamed'} · ${d.ip||'no IP'}</option>`;
  });
  selRow.innerHTML = `<select class="dev-select" id="dev-select">${opts}</select><span class="dev-select-count">${getVisibleCount(allDevs)} shown</span>`;
  panel.appendChild(selRow);

  // Bind selector
  selRow.querySelector('#dev-select').addEventListener('change', e=>{
    viewMode = e.target.value;
    renderDevicePanel();
  });

  // --- Render device cards based on view mode ---
  const visible = getVisibleDevices(allDevs);
  visible.forEach(d=> panel.appendChild(createDeviceCard(d)));
}

function getVisibleDevices(allDevs){
  if(viewMode === 'all') return allDevs;
  if(viewMode.startsWith('zone:')){
    const zid = viewMode.split(':')[1];
    return allDevs.filter(d=>d.zoneId===zid);
  }
  if(viewMode.startsWith('dev:')){
    const uid = viewMode.split(':')[1];
    return allDevs.filter(d=>d.uid===uid);
  }
  return allDevs;
}

function getVisibleCount(allDevs){
  return getVisibleDevices(allDevs).length;
}

function createDeviceCard(d){
  const card = document.createElement('div');
  card.className = 'dev-card';
  card.style.marginBottom = '8px';
  card.innerHTML = `<div class="dev-head"><span class="dev-dot"></span><span class="dev-name">${d.name||'Unnamed'}</span><span class="dev-ip">${d.ip||'\u2014'}</span><span class="dev-zone-tag">Zone ${d.zoneId.toUpperCase()}</span></div>`+
    `<div class="dev-sensors">`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-temp">--</span><span class="dev-s-lbl">Air <span class="dev-s-unit">°C</span></span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-hum">--</span><span class="dev-s-lbl">Humid <span class="dev-s-unit">%</span></span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-lux">--</span><span class="dev-s-lbl">Light <span class="dev-s-unit">lux</span></span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-soil">--</span><span class="dev-s-lbl">Soil <span class="dev-s-unit">%</span></span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-ph">--</span><span class="dev-s-lbl">pH</span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-ec">--</span><span class="dev-s-lbl">EC <span class="dev-s-unit">mS</span></span></div>`+
    `</div>`;
  return card;
}

function calcAverages(){
  const keys = Object.keys(deviceSensorData);
  if(keys.length===0) return {temp:'--',hum:'--',ph:'--',soil:'--'};
  let t=0,h=0,p=0,s=0;
  keys.forEach(k=>{
    const d = deviceSensorData[k];
    t+=d.temp||0; h+=d.hum||0; p+=d.ph||0; s+=d.soil||0;
  });
  const n = keys.length;
  return { temp:(t/n).toFixed(1), hum:Math.round(h/n), ph:(p/n).toFixed(1), soil:Math.round(s/n) };
}

renderDevicePanel();

// ====== SENSOR SIMULATION (PER-DEVICE) ======
// Replace with real WebSocket/fetch to each ESP32 IP later
function simulateSensors(){
  zones.forEach(z=>{
    (z.devices||[]).forEach((d,i)=>{
      const uid = z.id+'_'+i;
      const vals = {
        temp: parseFloat((22+Math.random()*4).toFixed(1)),
        hum: Math.floor(60+Math.random()*15),
        lux: Math.floor(700+Math.random()*300),
        soil: Math.floor(35+Math.random()*20),
        ph: parseFloat((6.0+Math.random()*1.5).toFixed(1)),
        ec: parseFloat((1.0+Math.random()*1.0).toFixed(1))
      };
      deviceSensorData[uid] = vals;
      // Update DOM if card is visible
      const u=(k,v)=>{const e=document.getElementById('dv-'+uid+'-'+k);if(e)e.textContent=v;};
      u('temp',vals.temp);
      u('hum',vals.hum);
      u('lux',vals.lux);
      u('soil',vals.soil);
      u('ph',vals.ph);
      u('ec',vals.ec);
    });
  });
  // Update summary bar
  const avg = calcAverages();
  ['temp','hum','ph','soil'].forEach(k=>{
    const el = document.querySelector(`.dev-sum-item:nth-child(${k==='temp'?1:k==='hum'?2:k==='ph'?3:4}) .dev-sum-val`);
    if(el) el.textContent = avg[k];
  });
}
simulateSensors();
setInterval(simulateSensors, 5000);

// ====== PROFILE PAGE ======
// Profile btn in topbar navigates to profile page
document.getElementById('btn-user').addEventListener('click', ()=>{
  switchPage('page-profile');
  updateProfileCounts();
});

// Load saved profile data
const defaultProfile = {
  fname: 'Plant',
  lname: 'Researcher',
  email: 'user@plantvision.ai',
  org: 'PlantVision Lab',
  location: 'Baghdad, Iraq'
};

let profileData = JSON.parse(localStorage.getItem('pv-profile')) || {...defaultProfile};

function loadProfile(){
  const f = document.getElementById('prof-fname');
  const l = document.getElementById('prof-lname');
  const e = document.getElementById('prof-email');
  const o = document.getElementById('prof-org');
  const loc = document.getElementById('prof-location');
  if(f) f.value = profileData.fname || '';
  if(l) l.value = profileData.lname || '';
  if(e) e.value = profileData.email || '';
  if(o) o.value = profileData.org || '';
  if(loc) loc.value = profileData.location || '';
  // Update display card
  const displayName = document.getElementById('profile-display-name');
  const displayEmail = document.getElementById('profile-display-email');
  const avatar = document.getElementById('profile-avatar-display');
  if(displayName) displayName.textContent = (profileData.fname||'')+' '+(profileData.lname||'');
  if(displayEmail) displayEmail.textContent = profileData.email || '';
  if(avatar){
    const initials = ((profileData.fname||'P')[0]+(profileData.lname||'V')[0]).toUpperCase();
    avatar.textContent = initials;
  }
}

function saveProfile(){
  const f = document.getElementById('prof-fname');
  const l = document.getElementById('prof-lname');
  const e = document.getElementById('prof-email');
  const o = document.getElementById('prof-org');
  const loc = document.getElementById('prof-location');
  profileData = {
    fname: f?f.value.trim():'',
    lname: l?l.value.trim():'',
    email: e?e.value.trim():'',
    org: o?o.value.trim():'',
    location: loc?loc.value.trim():''
  };
  localStorage.setItem('pv-profile', JSON.stringify(profileData));
  syncToServer('profile', profileData);
  loadProfile();
}

function updateProfileCounts(){
  const zc = document.getElementById('prof-zone-count');
  const dc = document.getElementById('prof-device-count');
  if(zc) zc.textContent = zones.length;
  if(dc){
    let total = 0;
    zones.forEach(z=> total += (z.devices||[]).length);
    dc.textContent = total;
  }
}

// Bind save button
const profileSaveBtn = document.getElementById('profile-save-btn');
if(profileSaveBtn){
  profileSaveBtn.addEventListener('click', ()=>{
    saveProfile();
    profileSaveBtn.textContent = '✓ Saved!';
    profileSaveBtn.style.background = 'var(--sage-mid)';
    setTimeout(()=>{
      profileSaveBtn.textContent = 'Save Changes';
      profileSaveBtn.style.background = '';
    }, 1500);
  });
}

// Edit profile button scrolls to the fields
const profileEditBtn = document.getElementById('profile-edit-btn');
if(profileEditBtn){
  profileEditBtn.addEventListener('click', ()=>{
    const fname = document.getElementById('prof-fname');
    if(fname) fname.focus();
  });
}

// Sign out (clears profile data for now)
const logoutBtn = document.getElementById('prof-logout');
if(logoutBtn){
  logoutBtn.addEventListener('click', ()=>{
    if(confirm('Sign out? Your local data will remain saved.')){
      switchPage('page-home');
    }
  });
}

// Export profile data
const exportBtn = document.getElementById('prof-export');
if(exportBtn){
  exportBtn.addEventListener('click', ()=>{
    const data = {
      profile: profileData,
      zones: zones,
      exportDate: new Date().toISOString()
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], {type:'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'plantvision-export.json'; a.click();
    URL.revokeObjectURL(url);
  });
}

// Load on init
loadProfile();

// ====== NOTIFICATION SYSTEM ======
const notifPanel = document.getElementById('notif-panel');
const notifList = document.getElementById('notif-list');
const notifEmpty = document.getElementById('notif-empty');
const notifBadge = document.getElementById('notif-badge');
const btnBell = document.getElementById('btn-bell');
const notifMarkAll = document.getElementById('notif-mark-all');
const notifClearAll = document.getElementById('notif-clear-all');

// Default notifications
const defaultNotifications = [
  { id:'n1', type:'alert', icon:'⚠️', title:'Fungus Detected — Zone D', desc:'Greenhouse zone shows signs of leaf spot fungus on 2 plants. Immediate attention recommended.', time: Date.now() - 4*3600000, read:false },
  { id:'n2', type:'scan', icon:'🔬', title:'Scan Complete — Monstera', desc:'Monstera deliciosa passed health check with 96.4% confidence. No diseases detected.', time: Date.now() - 7200000, read:false },
  { id:'n3', type:'zone', icon:'🌿', title:'Zone B Needs Water', desc:'Soil moisture in Herb Garden dropped below 30%. Consider watering basil and mint.', time: Date.now() - 8*3600000, read:false },
  { id:'n4', type:'sensor', icon:'📡', title:'ESP32-D3 Connected', desc:'New device ESP32-D3 (192.168.1.16) successfully paired with Zone D Greenhouse.', time: Date.now() - 18*3600000, read:true },
  { id:'n5', type:'system', icon:'⚙️', title:'Neural Engine Updated', desc:'AI model updated to v4.2.1. Detection accuracy improved by 3.2% across all species.', time: Date.now() - 86400000, read:true },
  { id:'n6', type:'scan', icon:'🔬', title:'Scan Complete — Pothos', desc:'Pothos Aureum passed health check with 99.1% confidence. Excellent condition.', time: Date.now() - 3600000, read:true },
];

let notifications = JSON.parse(localStorage.getItem('pv-notifications')) || [...defaultNotifications];
let notifIdCounter = parseInt(localStorage.getItem('pv-notif-counter')) || 100;

function saveNotifications(){
  localStorage.setItem('pv-notifications', JSON.stringify(notifications));
  localStorage.setItem('pv-notif-counter', notifIdCounter.toString());
  syncToServer('notifications', notifications);
  syncToServer('notifCounter', notifIdCounter);
}

function timeAgo(ts){
  const diff = Date.now() - ts;
  const mins = Math.floor(diff/60000);
  if(mins < 1) return 'Just now';
  if(mins < 60) return mins + 'm ago';
  const hrs = Math.floor(mins/60);
  if(hrs < 24) return hrs + 'h ago';
  const days = Math.floor(hrs/24);
  if(days === 1) return 'Yesterday';
  if(days < 7) return days + 'd ago';
  return new Date(ts).toLocaleDateString('en-US',{month:'short',day:'numeric'});
}

function getNotifIconClass(type){
  const map = { scan:'ni-scan', zone:'ni-zone', sensor:'ni-sensor', alert:'ni-alert', system:'ni-system' };
  return map[type] || 'ni-system';
}

function renderNotifications(animate){
  if(!notifList) return;
  notifList.innerHTML = '';

  if(notifications.length === 0){
    notifEmpty.style.display = 'flex';
    notifList.style.display = 'none';
  } else {
    notifEmpty.style.display = 'none';
    notifList.style.display = 'block';

    notifications.sort((a,b) => b.time - a.time);

    notifications.forEach((n, i) => {
      const item = document.createElement('div');
      item.className = 'notif-item' + (n.read ? '' : ' unread') + (animate ? ' slide-in' : '');
      if(animate) item.style.animationDelay = (i * 0.04) + 's';

      item.innerHTML =
        `<div class="notif-ico ${getNotifIconClass(n.type)}">${n.icon}</div>` +
        `<div class="notif-body">` +
          `<span class="notif-title">${n.title}</span>` +
          `<span class="notif-desc">${n.desc}</span>` +
          `<span class="notif-time mono">${timeAgo(n.time)}</span>` +
        `</div>` +
        `<button class="notif-dismiss" data-id="${n.id}" title="Dismiss">✕</button>`;

      // Click item to mark as read
      item.addEventListener('click', (e) => {
        if(e.target.closest('.notif-dismiss')) return;
        if(!n.read){
          n.read = true;
          item.classList.remove('unread');
          updateBadge();
          saveNotifications();
        }
      });

      notifList.appendChild(item);
    });

    // Bind dismiss buttons
    notifList.querySelectorAll('.notif-dismiss').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = btn.dataset.id;
        const item = btn.closest('.notif-item');
        item.style.transition = 'opacity .2s, transform .2s';
        item.style.opacity = '0';
        item.style.transform = 'translateX(20px)';
        setTimeout(() => {
          notifications = notifications.filter(n => n.id !== id);
          saveNotifications();
          renderNotifications(false);
          updateBadge();
        }, 200);
      });
    });
  }

  updateBadge();
}

function updateBadge(){
  const unread = notifications.filter(n => !n.read).length;
  if(unread > 0){
    notifBadge.textContent = unread > 9 ? '9+' : unread;
    notifBadge.classList.remove('hidden');
  } else {
    notifBadge.classList.add('hidden');
  }
}

// Toggle panel
btnBell.addEventListener('click', (e) => {
  e.stopPropagation();
  const isOpen = notifPanel.classList.contains('open');
  if(isOpen){
    notifPanel.classList.remove('open');
  } else {
    notifPanel.classList.add('open');
    renderNotifications(true);
  }
});

// Close on outside click
document.addEventListener('click', (e) => {
  if(!e.target.closest('.notif-anchor')){
    notifPanel.classList.remove('open');
  }
});

// Mark all read
notifMarkAll.addEventListener('click', (e) => {
  e.stopPropagation();
  notifications.forEach(n => n.read = true);
  saveNotifications();
  renderNotifications(false);
  // Brief visual feedback
  notifMarkAll.style.color = 'var(--sage)';
  setTimeout(() => notifMarkAll.style.color = '', 600);
});

// Clear all
notifClearAll.addEventListener('click', (e) => {
  e.stopPropagation();
  notifications = [];
  saveNotifications();
  renderNotifications(false);
});

// --- Push notification helper ---
function pushNotification(type, icon, title, desc){
  const n = {
    id: 'n' + (notifIdCounter++),
    type, icon, title, desc,
    time: Date.now(),
    read: false
  };
  notifications.unshift(n);
  // Cap at 50 notifications
  if(notifications.length > 50) notifications = notifications.slice(0, 50);
  saveNotifications();
  updateBadge();
  // Pulse badge
  notifBadge.classList.remove('pulse');
  void notifBadge.offsetWidth;
  notifBadge.classList.add('pulse');
  // If panel is open, re-render
  if(notifPanel.classList.contains('open')) renderNotifications(true);
}

// --- Hook into scan completion to generate notifications ---
const origResModalShow = resModal.classList.add.bind(resModal.classList);
const resObserver = new MutationObserver((mutations) => {
  mutations.forEach(m => {
    if(m.attributeName === 'class' && resModal.classList.contains('active')){
      const species = document.getElementById('r-species')?.textContent || 'Unknown';
      const conf = document.getElementById('r-conf')?.textContent || '—';
      const health = document.getElementById('r-hp')?.textContent || '—';
      pushNotification('scan', '🔬', `Scan Complete — ${species}`, `Health score: ${health}, Confidence: ${conf}. Analysis saved to scan log.`);
    }
  });
});
resObserver.observe(resModal, {attributes:true, attributeFilter:['class']});

// --- Periodic sensor threshold alerts ---
let lastSensorAlert = Date.now();
function checkSensorAlerts(){
  if(Date.now() - lastSensorAlert < 60000) return; // Max 1 alert per minute
  const allDevs = getAllDevices();
  allDevs.forEach(d => {
    const data = deviceSensorData[d.uid];
    if(!data) return;
    if(data.soil < 25){
      pushNotification('alert', '💧', `Low Soil Moisture — ${d.name}`, `Zone ${d.zoneId.toUpperCase()} sensor reads ${data.soil}% soil moisture. Plants may need watering.`);
      lastSensorAlert = Date.now();
    }
    if(data.temp > 32){
      pushNotification('alert', '🌡️', `High Temperature Alert — ${d.name}`, `Zone ${d.zoneId.toUpperCase()} reports ${data.temp}°C. Consider ventilation or shade.`);
      lastSensorAlert = Date.now();
    }
    if(data.ph < 5.5){
      pushNotification('sensor', '⚗️', `Low pH Warning — ${d.name}`, `Zone ${d.zoneId.toUpperCase()} soil pH at ${data.ph}. Optimal range is 6.0–7.0.`);
      lastSensorAlert = Date.now();
    }
  });
}
setInterval(checkSensorAlerts, 30000);

// Initial render
renderNotifications(false);

// ====== LOAD FROM SERVER ON STARTUP ======
// Hydrate app state from server so all devices share the same data
(async function hydrateFromServer(){
  const serverData = await loadFromServer();
  if(!serverData) return; // Offline or error — keep localStorage data

  // Theme
  if(serverData.theme){
    localStorage.setItem('pv-theme', serverData.theme);
    if(serverData.theme === 'light'){
      root.setAttribute('data-theme','light');
      pts.forEach(p => p.c = Math.random()>.6 ? '90,122,90' : '107,127,90');
    } else {
      root.removeAttribute('data-theme');
      pts.forEach(p => p.c = Math.random()>.6 ? '140,168,140' : '150,165,138');
    }
  }

  // Zones
  if(serverData.zones && serverData.zones.length > 0){
    zones = serverData.zones;
    localStorage.setItem('pv-zones', JSON.stringify(zones));
    renderZoneChips();
    renderMapMarkers();
    renderDevicePanel();
  }

  // Profile
  if(serverData.profile){
    profileData = serverData.profile;
    localStorage.setItem('pv-profile', JSON.stringify(profileData));
    loadProfile();
  }

  // Notifications
  if(serverData.notifications){
    notifications = serverData.notifications;
    localStorage.setItem('pv-notifications', JSON.stringify(notifications));
    if(serverData.notifCounter) notifIdCounter = serverData.notifCounter;
    localStorage.setItem('pv-notif-counter', notifIdCounter.toString());
    renderNotifications(false);
  }

  console.log('✓ Synced from server');
})();

// ====== UPTIME COUNTER ======
const appStartTime = Date.now();
setInterval(() => {
  const el = document.getElementById('set-uptime');
  if(!el) return;
  const diff = Date.now() - appStartTime;
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  el.textContent = h + 'h ' + m + 'm';
}, 10000);

// ====== HOME ENV STRIP (backend /sensor/latest + demo fallback) ======
const ENV_DEMO = { temp: '24.2', hum: '62', lux: 1842, soil: '54' };
let liveSensorReading = null;

async function updateEnvStrip(){
  const getEl = id => document.getElementById(id);
  if(typeof fetchSensorLatest === 'function' && window.PLANT_API_BASE){
    try {
      const data = await fetchSensorLatest();
      if(data.source === 'live' && data.reading){
        liveSensorReading = data.reading;
      }
    } catch (_) {
      /* keep last live reading or fall back to demo */
    }
  }

  let temp, hum, lux, soil;
  if(liveSensorReading){
    temp = Number(liveSensorReading.air_temperature).toFixed(1);
    hum = Math.round(liveSensorReading.air_humidity);
    lux = Math.round(liveSensorReading.light_lux);
    if(liveSensorReading.soil_humidity != null){
      soil = Math.round(liveSensorReading.soil_humidity);
    } else {
      soil = Number(liveSensorReading.soil_ec).toFixed(1);
    }
  } else {
    const avg = calcAverages();
    if(avg.temp !== '--'){
      temp = avg.temp;
      hum = avg.hum;
      soil = avg.soil;
      lux = Math.floor(1400 + Math.random() * 800);
    } else {
      temp = ENV_DEMO.temp;
      hum = ENV_DEMO.hum;
      lux = ENV_DEMO.lux;
      soil = ENV_DEMO.soil;
    }
  }

  if(getEl('env-s-temp')) getEl('env-s-temp').textContent = temp + '°C';
  if(getEl('env-s-hum')) getEl('env-s-hum').textContent = hum + '%';
  if(getEl('env-s-lux')) getEl('env-s-lux').textContent = lux + ' lx';
  if(getEl('env-s-soil')){
    const useEc = liveSensorReading && liveSensorReading.soil_humidity == null;
    getEl('env-s-soil').textContent = useEc ? soil + ' mS' : soil + '%';
  }
}
setInterval(updateEnvStrip, 5000);
setTimeout(updateEnvStrip, 1500);

// ====== QUICK ACTION BUTTONS ======
const actAddZone = document.getElementById('act-add-zone');
if(actAddZone) actAddZone.addEventListener('click', () => {
  switchPage('page-garden');
  setTimeout(() => document.getElementById('zone-add-btn')?.click(), 300);
});

const actExport = document.getElementById('act-export');
if(actExport) actExport.addEventListener('click', () => {
  document.getElementById('prof-export')?.click();
});
