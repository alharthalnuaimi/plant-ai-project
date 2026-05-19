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

// --- HUD confidence chip (live after scan, subtle demo idle) ---
setInterval(()=>{
  const c=document.getElementById('s-conf');
  const f=document.getElementById('sys-fps');
  if(f) f.textContent=Math.floor(58+Math.random()*4);
  if(!c) return;
  if(c.dataset.liveConf) return;
  c.textContent='CONF '+(92+Math.random()*7).toFixed(1)+'%';
},2200);

// --- Scan (FastAPI POST /predict) ---
const scanModal = document.getElementById('scan-modal');
const scanSourceModal = document.getElementById('scan-source-modal');
const cameraModal = document.getElementById('camera-modal');
const resModal  = document.getElementById('res-modal');
const mFill     = document.getElementById('m-fill');
const mLbl      = document.getElementById('m-lbl');
let timer = null;

const scanFileInput = document.createElement('input');
scanFileInput.type = 'file';
scanFileInput.accept = 'image/*';
scanFileInput.style.display = 'none';
document.body.appendChild(scanFileInput);

const camPreview = document.getElementById('cam-preview');
const camCanvas = document.getElementById('cam-canvas');
const camHint = document.getElementById('cam-hint');
const camCaptureBtn = document.getElementById('cam-capture');
const camUseBtn = document.getElementById('cam-use');
const camCancelBtn = document.getElementById('cam-cancel');
let camStream = null;
let capturedBlob = null;

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
  const confNum = (result.confidence ?? 0) * 100;
  const confPct = confNum.toFixed(1) + '%';
  const userOk = window.plantVisionSettings && typeof window.plantVisionSettings.meetsConfidenceThreshold === 'function'
    ? window.plantVisionSettings.meetsConfidenceThreshold(result.confidence)
    : result.accepted;
  const health = result.health || null;
  const inferMs = Math.round(result.inference_ms ?? 0) + ' ms';

  const titleEl = document.getElementById('r-title');
  const speciesEl = document.getElementById('r-species');
  const confEl = document.getElementById('r-conf');
  const hpEl = document.getElementById('r-hp');
  const riskEl = document.getElementById('r-risk');
  const survEl = document.getElementById('r-surv');
  const recEl = document.getElementById('r-rec');
  const waterEl = document.getElementById('r-water');

  const classLabel = result.class_name || result.disease_type || '';
  if(titleEl) titleEl.textContent = userOk ? 'Analysis Complete' : 'Low Confidence';
  if(speciesEl) speciesEl.textContent = classLabel ? `Cucumber · ${disease} (${classLabel})` : `Cucumber · ${disease}`;
  if(confEl) confEl.textContent = confPct;
  if(hpEl) hpEl.textContent = health ? health.plant_health + '%' : (userOk ? '—' : 'Low conf.');
  if(riskEl) riskEl.textContent = health ? health.disease_risk : inferMs;
  if(survEl) survEl.textContent = health ? health.survival_chance + '%' : '—';
  if(recEl) recEl.textContent = health ? health.recommendation : (result.stress_hint || 'Monitor plant and rescan if symptoms persist.');
  if(waterEl) waterEl.textContent = result.model_name || 'yolov8';

  if(window.plantAssistant && typeof window.plantAssistant.setLastScan === 'function'){
    window.plantAssistant.setLastScan(result);
  }

  const confChip = document.getElementById('s-conf');
  if(confChip){
    confChip.textContent = 'CONF ' + confPct;
    confChip.dataset.liveConf = '1';
  }

  if(window.plantVisionSettings){
    if(typeof window.plantVisionSettings.recordScanComplete === 'function') window.plantVisionSettings.recordScanComplete();
    if(typeof window.plantVisionSettings.playScanSound === 'function') window.plantVisionSettings.playScanSound();
  }

  scanModal.classList.remove('active');
  resModal.classList.add('active');
  if (window.plantAnalytics && typeof window.plantAnalytics.refresh === 'function') {
    window.plantAnalytics.refresh();
  }
  if (window.plantGarden && result.zone_id && typeof window.plantGarden.pulseZone === 'function') {
    window.plantGarden.pulseZone(result.zone_id);
  }
  if (window.plantProfile && typeof window.plantProfile.refresh === 'function') {
    window.plantProfile.refresh(false);
  }
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

function openScanSourceModal(){
  scanSourceModal?.classList.add('active');
}

function closeScanSourceModal(){
  scanSourceModal?.classList.remove('active');
}

function triggerScanUpload(){
  closeScanSourceModal();
  scanFileInput.value = '';
  scanFileInput.click();
}

function stopCameraStream(){
  if(camStream){
    camStream.getTracks().forEach(t => t.stop());
    camStream = null;
  }
  if(camPreview) camPreview.srcObject = null;
}

function closeCameraModal(){
  stopCameraStream();
  capturedBlob = null;
  if(camCanvas){
    camCanvas.hidden = true;
    const ctx = camCanvas.getContext('2d');
    if(ctx) ctx.clearRect(0, 0, camCanvas.width, camCanvas.height);
  }
  if(camPreview) camPreview.hidden = false;
  if(camCaptureBtn) camCaptureBtn.hidden = false;
  if(camUseBtn){
    camUseBtn.hidden = true;
    camUseBtn.disabled = false;
  }
  if(camHint) camHint.textContent = 'Point at a leaf, then capture';
  cameraModal?.classList.remove('active');
}

async function openCameraModal(){
  closeScanSourceModal();
  if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
    alert('Camera is not supported in this browser. Please upload an image instead.');
    triggerScanUpload();
    return;
  }
  try {
    const constraints = window.plantVisionSettings && typeof window.plantVisionSettings.getCameraConstraints === 'function'
      ? window.plantVisionSettings.getCameraConstraints()
      : { video: { facingMode: { ideal: 'environment' } }, audio: false };
    camStream = await navigator.mediaDevices.getUserMedia(constraints);
    if(window.plantVisionSettings && typeof window.plantVisionSettings.applyTorchIfNeeded === 'function'){
      await window.plantVisionSettings.applyTorchIfNeeded(camStream);
    }
    if(camPreview){
      camPreview.srcObject = camStream;
      camPreview.hidden = false;
    }
    capturedBlob = null;
    if(camUseBtn) camUseBtn.hidden = true;
    if(camCaptureBtn) camCaptureBtn.hidden = false;
    cameraModal?.classList.add('active');
  } catch (err) {
    console.warn('Camera permission error:', err);
    alert('Could not access the camera. Check permissions or upload an image instead.');
    triggerScanUpload();
  }
}

function captureCameraPhoto(){
  if(!camPreview || !camCanvas || !camStream) return;
  const w = camPreview.videoWidth;
  const h = camPreview.videoHeight;
  if(!w || !h) return;
  camCanvas.width = w;
  camCanvas.height = h;
  const ctx = camCanvas.getContext('2d');
  ctx.drawImage(camPreview, 0, 0, w, h);
  camCanvas.hidden = false;
  camPreview.hidden = true;
  camCanvas.toBlob(blob => {
    capturedBlob = blob;
    if(camHint) camHint.textContent = 'Review capture, then use photo';
    if(camUseBtn) camUseBtn.hidden = false;
    if(camCaptureBtn) camCaptureBtn.hidden = true;
  }, 'image/jpeg', 0.92);
}

function useCameraPhoto(){
  if(!capturedBlob){
    captureCameraPhoto();
    return;
  }
  const file = new File([capturedBlob], 'camera-capture.jpg', { type: 'image/jpeg' });
  closeCameraModal();
  runPlantPredict(file);
}

scanFileInput.addEventListener('change', () => {
  const file = scanFileInput.files && scanFileInput.files[0];
  if(file) runPlantPredict(file);
});

document.getElementById('scan-trigger')?.addEventListener('click', openScanSourceModal);
document.getElementById('act-scan')?.addEventListener('click', openScanSourceModal);
document.getElementById('scan-opt-camera')?.addEventListener('click', openCameraModal);
document.getElementById('scan-opt-upload')?.addEventListener('click', triggerScanUpload);
document.getElementById('scan-opt-cancel')?.addEventListener('click', closeScanSourceModal);
camCaptureBtn?.addEventListener('click', captureCameraPhoto);
camUseBtn?.addEventListener('click', useCameraPhoto);
camCancelBtn?.addEventListener('click', closeCameraModal);

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
    // Skip replaying entrance animations on analytics — avoids flicker on Data page
    const reduced = document.body.classList.contains('pv-reduced-motion');
    if(targetId !== 'page-data' && targetId !== 'page-settings' && !reduced){
      pg.querySelectorAll('.an').forEach(el=>{
        el.style.animation='none';
        el.offsetHeight;
        el.style.animation='';
      });
    }
    if(targetId==='page-home') animateCountUp();
  }
  if(window.plantAnalytics && typeof window.plantAnalytics.onNavigate === 'function'){
    window.plantAnalytics.onNavigate(targetId);
  }
  if(window.plantVisionSettings && typeof window.plantVisionSettings.onNavigate === 'function'){
    window.plantVisionSettings.onNavigate(targetId);
  }
  if(window.plantGarden && typeof window.plantGarden.onNavigate === 'function'){
    window.plantGarden.onNavigate(targetId);
  }
  if(window.plantProfile && typeof window.plantProfile.onNavigate === 'function'){
    window.plantProfile.onNavigate(targetId);
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
  { id:'a', zone_id:'zone_alpha', lat:33.3152, lng:44.3661, name:'Alfarabi University', plants:8, status:'Healthy', devices:[{name:'ESP32-A1',device_id:'esp32_001',ip:'192.168.1.10'}] },
  { id:'b', zone_id:'zone_beta', lat:33.3128, lng:44.3890, name:'Karrada Garden', plants:5, status:'At Risk', devices:[{name:'ESP32-B1',device_id:'esp32_b1',ip:'192.168.1.11'},{name:'ESP32-B2',device_id:'esp32_b2',ip:'192.168.1.12'}] },
  { id:'c', zone_id:'zone_gamma', lat:33.3400, lng:44.3650, name:'Mansour Nursery', plants:12, status:'Healthy', devices:[{name:'ESP32-C1',device_id:'esp32_c1',ip:'192.168.1.13'}] },
  { id:'d', zone_id:'zone_delta', lat:33.2950, lng:44.3800, name:'Jadriya Greenhouse', plants:3, status:'Critical', devices:[{name:'ESP32-D1',device_id:'esp32_d1',ip:'192.168.1.14'},{name:'ESP32-D2',device_id:'esp32_d2',ip:'192.168.1.15'},{name:'ESP32-D3',device_id:'esp32_d3',ip:'192.168.1.16'}] }
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
  if(s==='Offline') return 'off';
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
    chip.dataset.zoneLocal = z.id;
    chip.innerHTML = `<span class="zone-chip-dot zcd-${cls}"></span><span class="zone-chip-main"><span class="zone-chip-line"><span class="zone-chip-id mono">${z.id.toUpperCase()}</span> — ${z.name}</span><span class="zone-chip-meta"><span class="zone-chip-status zcs-${cls}">${z.status || 'Offline'}</span><span class="zone-chip-plants mono">${z.plants} plants</span></span></span><span class="zone-chip-count mono">${z.plants}</span><div class="zone-chip-actions"><button class="zone-chip-btn zb-edit" data-id="${z.id}" title="Edit">✎</button><button class="zone-chip-btn zb-del" data-id="${z.id}" title="Delete">✕</button></div>`;
    chip.addEventListener('click',(e)=>{
      if(e.target.closest('.zone-chip-btn')) return;
      const zid = z.zone_id || z.id;
      if(window.plantGarden && typeof window.plantGarden.selectZone === 'function'){
        window.plantGarden.selectZone(zid);
      } else if(gardenMap) gardenMap.flyTo([z.lat,z.lng],18,{duration:0.8});
    });
    list.appendChild(chip);
  });
  // Bind edit/delete buttons
  list.querySelectorAll('.zb-edit').forEach(b=>b.addEventListener('click',()=>openZoneModal(b.dataset.id)));
  list.querySelectorAll('.zb-del').forEach(b=>b.addEventListener('click',()=>deleteZone(b.dataset.id)));
}

function renderMapMarkers(){
  if(window.plantGarden) return;
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
  if(window.plantGarden && typeof window.plantGarden.onZonesChanged === 'function'){
    window.plantGarden.onZonesChanged();
  } else {
    renderDevicePanel();
  }
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
  if(window.plantGarden && typeof window.plantGarden.onZonesChanged === 'function'){
    window.plantGarden.onZonesChanged();
  } else {
    renderDevicePanel();
  }
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
    } else if(window.plantGarden && typeof window.plantGarden.hasSelection === 'function' && window.plantGarden.hasSelection()){
      window.plantGarden.clearSelection();
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
    setTimeout(()=>{ initMap(); if(gardenMap) gardenMap.invalidateSize(); initPOI(); },100);
  }
});
mapObs.observe(document.querySelector('.content'),{subtree:true,attributes:true,attributeFilter:['class']});

window.plantGardenBridge = {
  getZones: () => zones,
  getMap: () => gardenMap,
  getMarkers: () => mapMarkers,
  getAllDevices: getAllDevices,
  renderChips: renderZoneChips,
  isMapClickMode: () => mapClickMode,
};

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

function escapeChatHtml(text){
  const el = document.createElement('span');
  el.textContent = text;
  return el.innerHTML;
}

function addMsg(text, isUser){
  const div = document.createElement('div');
  div.className = `chat-msg ${isUser ? 'chat-msg-user' : 'chat-msg-bot'}`;
  const now = new Date();
  const time = now.getHours().toString().padStart(2,'0')+':'+now.getMinutes().toString().padStart(2,'0');
  div.innerHTML = `<div class="chat-bubble">${escapeChatHtml(text)}</div><span class="chat-time mono">${time}</span>`;
  chatBody.appendChild(div);
  chatBody.scrollTop = chatBody.scrollHeight;
}

function removeChatTyping(){
  const typing = document.getElementById('chat-typing');
  if(typing) typing.remove();
}

function formatScanChatMessage(result){
  const disease = (result.disease || 'unknown').replace(/_/g, ' ');
  const confPct = ((result.confidence ?? 0) * 100).toFixed(1);
  const label = disease.charAt(0).toUpperCase() + disease.slice(1);
  const h = result.health;
  let msg;
  if(result.accepted === false){
    msg = `Scan complete: ${label} detected with ${confPct}% confidence (low confidence — try another angle or better lighting).`;
  } else {
    msg = `Scan complete: Cucumber ${label} detected with ${confPct}% confidence.`;
  }
  if(h){
    msg += ` Plant health ${h.plant_health}%, risk ${h.disease_risk}. ${h.recommendation}`;
  }
  return msg;
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
  setTimeout(async ()=>{
    const typing = document.getElementById('chat-typing');
    if(typing) typing.remove();
    let reply = null;
    if(window.plantAssistant && typeof window.plantAssistant.getContextualReply === 'function'){
      reply = window.plantAssistant.getContextualReply(text);
    }
    if(!reply){
      if(window.plantAssistant && typeof window.plantAssistant.refreshContext === 'function'){
        await window.plantAssistant.refreshContext();
        reply = window.plantAssistant.getContextualReply(text);
      }
    }
    addMsg(reply || getBotReply(text), false);
  }, 800 + Math.random()*600);
}

chatSend.addEventListener('click', sendMsg);
chatInput.addEventListener('keydown', e=>{ if(e.key==='Enter') sendMsg(); });

// ====== AI CHAT — camera scan ======
const chatCamBtn = document.getElementById('chat-cam-btn');
const chatCamPanel = document.getElementById('chat-cam-panel');
const chatCamPreview = document.getElementById('chat-cam-preview');
const chatCamCanvas = document.getElementById('chat-cam-canvas');
const chatCamHint = document.getElementById('chat-cam-hint');
const chatCamCaptureBtn = document.getElementById('chat-cam-capture');
const chatCamUseBtn = document.getElementById('chat-cam-use');
const chatCamCancelBtn = document.getElementById('chat-cam-cancel');
let chatCamStream = null;
let chatCapturedBlob = null;

function stopChatCameraStream(){
  if(chatCamStream){
    chatCamStream.getTracks().forEach(t => t.stop());
    chatCamStream = null;
  }
  if(chatCamPreview) chatCamPreview.srcObject = null;
}

function closeChatCameraPanel(){
  stopChatCameraStream();
  chatCapturedBlob = null;
  if(chatCamCanvas){
    chatCamCanvas.hidden = true;
    const ctx = chatCamCanvas.getContext('2d');
    if(ctx) ctx.clearRect(0, 0, chatCamCanvas.width, chatCamCanvas.height);
  }
  if(chatCamPreview) chatCamPreview.hidden = false;
  if(chatCamCaptureBtn) chatCamCaptureBtn.hidden = false;
  if(chatCamUseBtn) chatCamUseBtn.hidden = true;
  if(chatCamHint) chatCamHint.textContent = 'Point at a leaf, then capture';
  if(chatCamPanel){
    chatCamPanel.classList.remove('active');
    chatCamPanel.setAttribute('aria-hidden', 'true');
  }
}

async function openChatCameraPanel(){
  if(!chatCamPanel) return;
  chatWidget.classList.add('open');
  if(!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia){
    addMsg('Camera is not supported in this browser. Use the Home scan upload instead.', false);
    return;
  }
  try {
    chatCamStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
    if(chatCamPreview){
      chatCamPreview.srcObject = chatCamStream;
      chatCamPreview.hidden = false;
    }
    chatCapturedBlob = null;
    if(chatCamUseBtn) chatCamUseBtn.hidden = true;
    if(chatCamCaptureBtn) chatCamCaptureBtn.hidden = false;
    chatCamPanel.classList.add('active');
    chatCamPanel.setAttribute('aria-hidden', 'false');
  } catch (err) {
    console.warn('Chat camera error:', err);
    addMsg('Camera access was denied. You can still upload an image.', false);
    closeChatCameraPanel();
  }
}

function captureChatPhoto(){
  if(!chatCamPreview || !chatCamCanvas || !chatCamStream) return;
  const w = chatCamPreview.videoWidth;
  const h = chatCamPreview.videoHeight;
  if(!w || !h) return;
  chatCamCanvas.width = w;
  chatCamCanvas.height = h;
  chatCamCanvas.getContext('2d').drawImage(chatCamPreview, 0, 0, w, h);
  chatCamCanvas.hidden = false;
  chatCamPreview.hidden = true;
  chatCamCanvas.toBlob(blob => {
    chatCapturedBlob = blob;
    if(chatCamHint) chatCamHint.textContent = 'Review capture, then use photo';
    if(chatCamUseBtn) chatCamUseBtn.hidden = false;
    if(chatCamCaptureBtn) chatCamCaptureBtn.hidden = true;
  }, 'image/jpeg', 0.92);
}

async function runChatPlantPredict(file){
  closeChatCameraPanel();
  addMsg('Scanning plant image…', true);
  showTyping();
  try {
    const result = await predictPlantImage(file);
    removeChatTyping();
    addMsg(formatScanChatMessage(result), false);
    showPredictResult(result);
  } catch (e) {
    removeChatTyping();
    const msg = e.message || 'Could not reach the vision API.';
    addMsg('Scan failed: ' + msg, false);
    showScanError(msg);
  }
}

function useChatPhoto(){
  if(!chatCapturedBlob){
    captureChatPhoto();
    return;
  }
  const file = new File([chatCapturedBlob], 'chat-camera.jpg', { type: 'image/jpeg' });
  runChatPlantPredict(file);
}

chatCamBtn?.addEventListener('click', e => {
  e.stopPropagation();
  openChatCameraPanel();
});
chatCamCaptureBtn?.addEventListener('click', e => { e.stopPropagation(); captureChatPhoto(); });
chatCamUseBtn?.addEventListener('click', e => { e.stopPropagation(); useChatPhoto(); });
chatCamCancelBtn?.addEventListener('click', e => { e.stopPropagation(); closeChatCameraPanel(); });

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
    `<div class="dev-sensor-rows">`+
    `<div class="dev-sensors dev-sensors-env">`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-temp">--</span><span class="dev-s-lbl">Air <span class="dev-s-unit">°C</span></span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-hum">--</span><span class="dev-s-lbl">Humid <span class="dev-s-unit">%</span></span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-lux">--</span><span class="dev-s-lbl">Light <span class="dev-s-unit">lux</span></span></div>`+
    `</div>`+
    `<div class="dev-sensors dev-sensors-soil">`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-soiltemp">--</span><span class="dev-s-lbl">Soil <span class="dev-s-unit">°C</span></span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-soil">--</span><span class="dev-s-lbl">Soil <span class="dev-s-unit">%</span></span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-ph">--</span><span class="dev-s-lbl">pH</span></div>`+
    `<div class="dev-s"><span class="dev-s-val" id="dv-${d.uid}-ec">--</span><span class="dev-s-lbl">EC <span class="dev-s-unit">mS</span></span></div>`+
    `</div></div>`;
  return card;
}

function calcAverages(){
  const keys = Object.keys(deviceSensorData);
  if(keys.length===0) return {temp:'--',hum:'--',ph:'--',soil:'--',soilTemp:'--',ec:'--',lux:'--'};
  let t=0,h=0,p=0,s=0,st=0,ec=0,lux=0;
  keys.forEach(k=>{
    const d = deviceSensorData[k];
    t+=d.temp||0; h+=d.hum||0; p+=d.ph||0; s+=d.soil||0;
    st+=d.soilTemp||0; ec+=d.ec||0; lux+=d.lux||0;
  });
  const n = keys.length;
  return {
    temp:(t/n).toFixed(1),
    hum:Math.round(h/n),
    ph:(p/n).toFixed(1),
    soil:Math.round(s/n),
    soilTemp:(st/n).toFixed(1),
    ec:(ec/n).toFixed(1),
    lux:Math.round(lux/n),
  };
}

if(!window.plantGarden) renderDevicePanel();

// ====== SENSOR SIMULATION (PER-DEVICE) ======
// Replace with real WebSocket/fetch to each ESP32 IP later
function simulateSensors(){
  if(window.plantGarden) return;
  zones.forEach(z=>{
    (z.devices||[]).forEach((d,i)=>{
      const uid = z.id+'_'+i;
      const vals = {
        temp: parseFloat((22+Math.random()*4).toFixed(1)),
        hum: Math.floor(60+Math.random()*15),
        lux: Math.floor(700+Math.random()*300),
        soilTemp: parseFloat((20+Math.random()*8).toFixed(1)),
        soil: Math.floor(35+Math.random()*20),
        ph: parseFloat((6.0+Math.random()*1.5).toFixed(1)),
        ec: parseFloat((1.0+Math.random()*1.0).toFixed(1))
      };
      deviceSensorData[uid] = vals;
      const u=(k,v)=>{const e=document.getElementById('dv-'+uid+'-'+k);if(e)e.textContent=v;};
      u('temp',vals.temp);
      u('hum',vals.hum);
      u('lux',vals.lux);
      u('soiltemp',vals.soilTemp);
      u('soil',vals.soil);
      u('ph',vals.ph);
      u('ec',vals.ec);
    });
  });
  const avg = calcAverages();
  ['temp','hum','ph','soil'].forEach(k=>{
    const el = document.querySelector(`.dev-sum-item:nth-child(${k==='temp'?1:k==='hum'?2:k==='ph'?3:4}) .dev-sum-val`);
    if(el) el.textContent = avg[k];
  });
}
simulateSensors();
const sensorSimTimer = setInterval(simulateSensors, 5000);
window._stopSensorSimulation = () => clearInterval(sensorSimTimer);

// Profile page: profile.js (plantProfile)

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
      const risk = document.getElementById('r-risk')?.textContent || '—';
      pushNotification('scan', '🔬', `Scan Complete — ${species}`, `Health: ${health}, Risk: ${risk}, Confidence: ${conf}.`);
    }
  });
});
resObserver.observe(resModal, {attributes:true, attributeFilter:['class']});

// --- Periodic sensor threshold alerts ---
let lastSensorAlert = Date.now();
function checkSensorAlerts(){
  const cfg = window.plantVisionSettings && typeof window.plantVisionSettings.get === 'function'
    ? window.plantVisionSettings.get() : null;
  if(cfg && !cfg.notifications) return;
  if(Date.now() - lastSensorAlert < 60000) return; // Max 1 alert per minute
  const soilTh = cfg ? cfg.soilMoistureAlertLow : 25;
  const tempTh = cfg ? cfg.tempAlertC : 32;
  const phMin = cfg ? cfg.phMin : 5.5;
  const allDevs = getAllDevices();
  allDevs.forEach(d => {
    const data = deviceSensorData[d.uid];
    if(!data) return;
    if(data.soil < soilTh){
      pushNotification('alert', '💧', `Low Soil Moisture — ${d.name}`, `Zone ${d.zoneId.toUpperCase()} sensor reads ${data.soil}% soil moisture. Plants may need watering.`);
      lastSensorAlert = Date.now();
    }
    if(data.temp > tempTh){
      pushNotification('alert', '🌡️', `High Temperature Alert — ${d.name}`, `Zone ${d.zoneId.toUpperCase()} reports ${data.temp}°C. Consider ventilation or shade.`);
      lastSensorAlert = Date.now();
    }
    if(data.ph < phMin){
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

// ====== ZONE SENSORS (backend /sensor/latest + demo fallback) ======
const ENV_DEMO = {
  air_temperature: 25.2,
  air_humidity: 73,
  light_lux: 780,
  soil_temperature: 28.2,
  soil_humidity: 46,
  soil_ph: 6.1,
  soil_ec: 1.6,
};
let liveSensorReading = null;

function resolveSensorDisplayValues(){
  if(liveSensorReading){
    return {
      air_temperature: Number(liveSensorReading.air_temperature).toFixed(1),
      air_humidity: Math.round(liveSensorReading.air_humidity),
      light_lux: Math.round(liveSensorReading.light_lux),
      soil_temperature: Number(liveSensorReading.soil_temperature).toFixed(1),
      soil_humidity: Math.round(liveSensorReading.soil_humidity),
      soil_ph: Number(liveSensorReading.soil_ph).toFixed(1),
      soil_ec: Number(liveSensorReading.soil_ec).toFixed(1),
      isLive: true,
    };
  }
  const avg = calcAverages();
  if(avg.temp !== '--'){
    return {
      air_temperature: avg.temp,
      air_humidity: avg.hum,
      light_lux: Math.floor(700 + Math.random() * 300),
      soil_temperature: avg.soilTemp !== '--' ? avg.soilTemp : ENV_DEMO.soil_temperature,
      soil_humidity: avg.soil,
      soil_ph: avg.ph,
      soil_ec: avg.ec !== '--' ? avg.ec : ENV_DEMO.soil_ec,
      isLive: false,
    };
  }
  return { ...ENV_DEMO, isLive: false };
}

let lastZoneSensorKey = '';

function applyZoneSensorDisplay(values){
  const set = (id, text) => {
    const el = document.getElementById(id);
    if(el && el.textContent !== String(text)) el.textContent = text;
  };
  const key = [
    values.air_temperature, values.air_humidity, values.light_lux,
    values.soil_temperature, values.soil_humidity, values.soil_ph, values.soil_ec,
    values.isLive,
  ].join('|');
  if(key === lastZoneSensorKey) return;
  lastZoneSensorKey = key;
  set('zs-air-temp', values.air_temperature);
  set('zs-air-hum', values.air_humidity);
  set('zs-light', values.light_lux);
  set('zs-soil-temp', values.soil_temperature);
  set('zs-soil-hum', values.soil_humidity);
  set('zs-ph', values.soil_ph);
  set('zs-ec', values.soil_ec);
  set('env-s-temp', values.air_temperature + '°C');
  set('env-s-hum', values.air_humidity + '%');
  set('env-s-lux', values.light_lux + ' lx');
  set('env-s-soil', values.soil_humidity + '%');
  const liveEl = document.getElementById('zone-sensor-live');
  if(liveEl){
    liveEl.textContent = values.isLive ? '● LIVE' : '● DEMO';
    liveEl.classList.toggle('is-demo', !values.isLive);
  }
}

async function updateEnvStrip(force){
  if(typeof fetchSensorLatest === 'function' && window.PLANT_API_BASE){
    try {
      const data = await fetchSensorLatest();
      if(data.source === 'live' && data.reading){
        liveSensorReading = data.reading;
        if(window.plantVisionSettings && typeof window.plantVisionSettings.refreshStatus === 'function' && force){
          window.plantVisionSettings.refreshStatus();
        }
      }
    } catch (_) {
      /* keep last live reading or fall back to demo */
    }
  }
  applyZoneSensorDisplay(resolveSensorDisplayValues());
}

let sensorPollTimer = null;
function getSensorPollMs(){
  const cfg = window.plantVisionSettings && typeof window.plantVisionSettings.get === 'function'
    ? window.plantVisionSettings.get() : null;
  const sec = cfg && cfg.sensorPollSec ? cfg.sensorPollSec : 5;
  return Math.max(3000, sec * 1000);
}
function restartSensorPolling(){
  if(sensorPollTimer) clearInterval(sensorPollTimer);
  updateEnvStrip(true);
  sensorPollTimer = setInterval(() => updateEnvStrip(false), getSensorPollMs());
}
window.plantSensorRefresh = (force) => updateEnvStrip(Boolean(force));
restartSensorPolling();
window.addEventListener('plantvision:settings-changed', () => restartSensorPolling());

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
