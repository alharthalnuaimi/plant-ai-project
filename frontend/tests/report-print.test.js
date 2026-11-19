// Printable (save-as-PDF) scan report. Run: node --test frontend/tests/*.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP = path.join(__dirname, '..', 'mobile-app');
const ARABIC = /[؀-ۿ]/;

function load(lang) {
  const store = new Map([['pv-lang', lang]]);
  const window = {};
  const document = {
    documentElement: { setAttribute() {} }, readyState: 'loading', title: '',
    addEventListener() {}, querySelectorAll: () => [],
  };
  const ctx = { window, document, localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) }, URL };
  for (const f of ['i18n-ar.js', 'i18n.js', 'report-print.js']) {
    vm.runInNewContext(fs.readFileSync(path.join(APP, f), 'utf8'), ctx);
  }
  return window;
}

const REPORT = {
  generated_at: '2026-11-19T10:00:00.000Z',
  app: 'PlantVision',
  language: 'ar',
  scan: { result_received_at: '2026-11-19T09:59:00.000Z', scan_source: 'upload', image_url: null },
  plant_identification: {
    common_name: 'Cucumber', scientific_name: 'Cucumis sativus', family: 'Cucurbitaceae', genus: 'Cucumis',
    plant_id_confidence_pct: 90, source: 'gemini',
  },
  diagnosis: {
    health_status: 'Possible disease', health_category: 'possible_disease', condition: 'Powdery Mildew',
    condition_category: 'fungal', diagnosis_status: 'diseased', severity: 'moderate',
    ai_diagnosis_confidence_pct: 82, confidence_kind: 'model_self_reported',
    summary: 'White powdery patches.', symptoms: [{ finding: 'White patches <script>x</script>', category: 'fungal_sign', certainty: 'confirmed' }],
    alternative_diagnoses: [], uncertainties: ['Undersides not visible.'], image_quality: 'good',
  },
  localized: {
    condition: 'البياض الدقيقي (Powdery Mildew)',
    summary: 'بقع بيضاء مسحوقية على الأوراق.',
    recommended_action: 'أزل الأوراق المصابة.',
    observations: ['بقع بيضاء على السطح العلوي'],
    uncertainties: ['السطح السفلي غير ظاهر.'],
    alternative_diagnoses: [],
    plant_common_name: 'الخيار',
  },
  recommendations: { gemini_recommended_action: 'Remove affected leaves.', ai_analysis: 'تحليل عربي من Gemini.' },
  environment: { air_temperature: '24.0°C', air_humidity: '62%', light: '—', soil_humidity: '—', soil_ph: '6.4', soil_ec: '—' },
  ai_model: { provider: 'google_gemini', model: 'gemini-3.5-flash', prompt_version: 'gemini-v3' },
  context: { user_id: 'demo_user', zone_id: 'zone_alpha', device_id: 'esp32_001', plant_id: 'cucumber_001' },
};

test('Arabic report is a right-to-left Arabic document', () => {
  const w = load('ar');
  const html = w.pvBuildPrintableReport(REPORT);
  assert.match(html, /<html lang="ar" dir="rtl">/);
  assert.match(html, /IBM\+Plex\+Sans\+Arabic/);
  assert.ok(html.includes('البياض الدقيقي (Powdery Mildew)'), 'uses the Arabic condition');
  assert.ok(html.includes('بقع بيضاء مسحوقية على الأوراق.'), 'uses the Arabic summary');
  assert.ok(html.includes('الخيار'), 'uses the Arabic plant name');
  assert.ok(html.includes('<bdi dir="ltr" class="sci">Cucumis sativus</bdi>'), 'keeps the scientific name LTR');
  assert.ok(html.includes('تحليل عربي من Gemini.'));
  assert.match(html, /تقرير/);
});

test('English report keeps the English layout and text', () => {
  const w = load('en');
  const html = w.pvBuildPrintableReport({ ...REPORT, language: 'en', localized: null });
  assert.match(html, /<html lang="en" dir="ltr">/);
  assert.ok(html.includes('Powdery Mildew'));
  assert.ok(html.includes('White powdery patches.'));
  assert.ok(!/البياض/.test(html));
  assert.ok(html.includes('Plant Identification'));
});

test('report text is HTML-escaped', () => {
  const w = load('en');
  const html = w.pvBuildPrintableReport({ ...REPORT, language: 'en', localized: null });
  assert.ok(!html.includes('<script>x</script>'));
  assert.ok(html.includes('&lt;script&gt;'));
});

test('missing values render as a dash, never invented', () => {
  const w = load('ar');
  const html = w.pvBuildPrintableReport({ ...REPORT, plant_identification: { common_name: null }, localized: null, diagnosis: { health_category: 'uncertain', health_status: 'Uncertain — image insufficient' } });
  assert.ok(html.includes('—'));
  assert.match(html, ARABIC);
});
