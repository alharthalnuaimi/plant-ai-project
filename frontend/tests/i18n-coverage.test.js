// Arabic localization: coverage of JS-generated strings, Arabic grammar
// (plural forms, gender), backend error messages and report fallbacks.
// Run: node --test frontend/tests/*.test.js
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP = path.join(__dirname, '..', 'mobile-app');
const ARABIC = /[؀-ۿ]/;

function load(lang = 'en', extra = []) {
  const store = new Map([['pv-lang', lang]]);
  const window = { PLANT_API_BASE: 'http://api.test' };
  const document = {
    documentElement: { setAttribute() {} }, readyState: 'loading', title: '',
    addEventListener() {}, querySelectorAll: () => [],
  };
  const ctx = { window, document, URL, localStorage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) } };
  for (const f of ['i18n-ar.js', 'i18n.js', ...extra]) vm.runInNewContext(fs.readFileSync(path.join(APP, f), 'utf8'), ctx);
  return window;
}

test('counts use correct Arabic plural forms', () => {
  const { pvI18n } = load('ar');
  const cases = {
    '1m ago': 'منذ دقيقة', '2h ago': 'منذ ساعتين', '5m ago': 'منذ 5 دقائق', '11d ago': 'منذ 11 يوماً',
    '1 scan': 'فحص واحد', '3 scans': '3 فحوصات', '2 Zones Active': 'منطقتان نشطتان',
    '7 devices': '7 أجهزة', '12 plants': '12 نبتة', '4 entries': '4 إدخالات',
  };
  for (const [en, ar] of Object.entries(cases)) assert.equal(pvI18n.t(en), ar, en);
});

test('home hero risk line agrees in gender and handles lowercase values', () => {
  const { pvI18n } = load('ar');
  assert.equal(pvI18n.t('Risk Low · Env Medium'), 'الخطر: منخفض · الإجهاد البيئي: متوسط');
  assert.equal(pvI18n.t('Risk medium · Env low'), 'الخطر: متوسط · الإجهاد البيئي: منخفض');
  assert.equal(pvI18n.t('Critical'), 'حرجة'); // status labels are feminine like سليمة / معرّضة للخطر
});

test('every backend AI error message has an Arabic copy, also inside "Chat error:"', () => {
  const { pvI18n } = load('ar');
  const src = fs.readFileSync(path.join(__dirname, '..', '..', 'backend', 'services', 'gemini', 'errors.py'), 'utf8');
  const msgs = [...src.matchAll(/default_message = \(?\s*((?:"[^"]*"\s*)+)\)?/g)]
    .map((m) => [...m[1].matchAll(/"([^"]*)"/g)].map((x) => x[1]).join(''));
  assert.ok(msgs.length >= 10);
  for (const m of msgs) assert.match(pvI18n.t(m), ARABIC, m);
  assert.doesNotMatch(pvI18n.t('Chat error: The AI service is temporarily unavailable. Please retry.'), /[A-Za-z]{3,}/);
  assert.match(pvI18n.t('Could not reach backend. Is FastAPI running on http://x:8000?'), ARABIC);
});

test('chat requests carry lang=ar', () => {
  const { pvI18n } = load('ar');
  assert.equal(pvI18n.withLang('http://api.test/chat'), 'http://api.test/chat?lang=ar');
});

test('pick() prefers the stored Arabic field only in Arabic', () => {
  const { pvI18n } = load('en');
  const scan = { disease: 'Rose Black Spot', disease_localized: 'التبقع الأسود في الورد' };
  assert.equal(pvI18n.pick(scan, 'disease'), 'Rose Black Spot');
  pvI18n.setLang('ar');
  assert.equal(pvI18n.pick(scan, 'disease'), 'التبقع الأسود في الورد');
  assert.equal(pvI18n.pick({ disease: 'Leaf Spot' }, 'disease'), 'Leaf Spot'); // DOM translator handles known names
  assert.equal(pvI18n.pick(null, 'disease'), undefined);
});

test('toArabic() translates known names regardless of the UI language', () => {
  const { pvI18n } = load('en');
  assert.equal(pvI18n.toArabic('Powdery Mildew'), 'البياض الدقيقي');
  assert.equal(pvI18n.toArabic('Cucumber'), 'الخيار');
  assert.equal(pvI18n.toArabic('Rose Black Spot'), 'Rose Black Spot');
});

// ----------------------------------------------------------- report fallback

const REPORT = {
  generated_at: '2026-11-19T10:00:00.000Z', language: 'ar',
  plant_identification: { common_name: 'Cucumber', scientific_name: 'Cucumis sativus', family: 'Cucurbitaceae', genus: 'Cucumis' },
  diagnosis: { health_category: 'possible_disease', condition: 'Powdery Mildew', condition_category: 'fungal', severity: 'moderate' },
  localized: null, recommendations: {}, environment: {}, context: {}, ai_model: {},
};

test('Arabic report translates known disease and plant names when there is no Arabic block', () => {
  const w = load('ar', ['report-print.js']);
  const html = w.pvBuildPrintableReport(REPORT);
  assert.ok(html.includes('البياض الدقيقي'), 'known disease name translated');
  assert.ok(html.includes('الخيار'), 'known plant name translated');
  assert.ok(!html.includes('<td>Powdery Mildew</td>'), 'no silent English fallback');
  assert.ok(html.includes('<bdi dir="ltr" class="sci">Cucumis sativus</bdi>'), 'scientific name kept');
});

test('Arabic report from an English page still translates names', () => {
  const w = load('en', ['report-print.js']);
  const html = w.pvBuildPrintableReport(REPORT);
  assert.ok(html.includes('البياض الدقيقي') && html.includes('الخيار'));
});

test('English report keeps English names', () => {
  const w = load('ar', ['report-print.js']);
  const html = w.pvBuildPrintableReport({ ...REPORT, language: 'en' });
  assert.ok(html.includes('<td>Powdery Mildew</td>') && html.includes('<td>Cucumber</td>'));
  assert.ok(!html.includes('البياض'));
});

test('unknown Gemini condition names are shown as given', () => {
  const w = load('ar', ['report-print.js']);
  const html = w.pvBuildPrintableReport({ ...REPORT, diagnosis: { ...REPORT.diagnosis, condition: 'Rose Black Spot' } });
  assert.ok(html.includes('Rose Black Spot'));
});

// ------------------------------------------------- JS-generated string coverage

// Literals that are not user-facing, each with the reason.
const IGNORED = new Map([
  // fragments rebuilt from concatenation and translated whole by a pattern
  ['No', 'fragment of "No <category> found nearby…"'],
  // identifiers / protocol values compared in code, never shown
  ['Content-Type', 'HTTP header'], ['HTTP', 'prefix of "HTTP <status>" when the server sent no message'],
  ['DOMContentLoaded', 'DOM event name'], ['Enter', 'keyboard key name'],
  ['OverconstrainedError', 'DOMException name'], ['NotFoundError', 'DOMException name'], ['NotReadableError', 'DOMException name'],
  ['NotAllowedError', 'DOMException name'], ['SecurityError', 'DOMException name'],
  ['PLANT_USER_ID', 'window property name'], ['PLANT_ZONE_ID', 'window property name'], ['PLANT_DEVICE_ID', 'window property name'],
  ['IBM Plex Mono', 'font family'], ['2px 6px', 'CSS value'], ['opacity .2s, transform .2s', 'CSS value'], ['opacity .3s, transform .3s', 'CSS value'],
  ['No API base URL', 'internal error value, never rendered'], ['Cucumis sativus', 'scientific name stays Latin'],
  ['PREPROCESS', 'progress tag, shown through the "<TAG> · N%" pattern'], ['TEXTURE', 'progress tag'], ['CLASSIFY', 'progress tag'], ['HEALTH', 'progress tag'],
  ['CONF', 'shown through the "CONF N%" pattern'], ['DB', 'sidebar chip abbreviation (technical)'], ['KB', 'unit (technical)'],
  // map tile attribution (legal notice, stays as published)
  ['CARTO', 'map attribution'], ['OSM', 'map attribution'], ['© OSM', 'map attribution'], ['OpenTopoMap', 'map attribution'],
  ['© Esri, Maxar, Earthstar Geographics', 'map attribution'],
  ['HTTP 7', 'raw HTTP status, only when the server sent no message'],
  ['7\\n\\n(Assistant: 7)', 'only for non-Gemini reply sources, which /chat no longer returns'],
  // device names in the default zones are IDs
  ['ESP32-A1', 'device ID'], ['ESP32-B1', 'device ID'], ['ESP32-B2', 'device ID'], ['ESP32-C1', 'device ID'],
  ['ESP32-D1', 'device ID'], ['ESP32-D2', 'device ID'], ['ESP32-D3', 'device ID'],
  // lower-case match lists (search aliases, "unclassified" sets), compared not shown
  ['no disease', 'match list'], ['not assessable', 'match list'], ['pending analysis', 'match list'], ['zone alpha', 'search alias'],
  ['zone beta', 'search alias'], ['zone gamma', 'search alias'], ['zone delta', 'search alias'], ['at risk', 'search alias'],
  ['no sensor', 'search alias'], ['ai insight', 'alert category matcher'], ['backend unreachable', 'debug log reason'],
  // question sent to Gemini (not displayed); Gemini is told separately to answer in Arabic
  ['I just scanned my 7.', 'prompt text for Gemini'], ['The Gemini photo diagnosis is: "7".', 'prompt text for Gemini'],
  ['Using the diagnosis and the current sensor readings, explain what is going on', 'prompt text for Gemini'],
  ['and what I should do to take care of this plant right now.', 'prompt text for Gemini'],
  // legacy dual-model banner: only when gemini_agrees === false, which the backend never sends any more
  ['YOLOv8: 7 (7)', 'unreachable legacy banner'], ['Secondary check suggests: 7', 'unreachable legacy banner'],
]);
// Defined but unreachable from any screen (chat goes to Gemini only).
const UNUSED_BLOCK_START = /^(function (getBotReply|buildQuickActionCard)\b|const botResponses = \[)/;

function textNodes(line) {
  // a string argument like _pick(scan, "disease") is part of an expression, not text
  line = line.replace(/(\w\s*\([^()'"`]*,\s*)(["'`])[^"'`]*\2(\s*\))/g, '$1ARG$3');
  // Literals in order. Concatenations ("a" + expr + "b") are rebuilt with the
  // sample value 7, then split on HTML tags into the text nodes the DOM
  // translator will see. Each node is returned as alternatives: with the
  // neighbouring value (e.g. "7s ago") and bare (for helpers returning HTML).
  const lits = [...line.matchAll(/(["'`])((?:(?!\1)[^\\\n]|\\.)*)\1/g)];
  const groups = [];
  let cur = null; let bare = null; let end = 0;
  for (const m of lits) {
    const between = line.slice(end, m.index);
    const body = m[2].replace(/\$\{[^}]*\}/g, '7').split('\\u26a0').join('\u26a0').replace(/\\"/g, '"');
    if (cur !== null && /^\s*\+\s*$/.test(between)) { cur += body; bare += body; }
    else if (cur !== null && /^\s*\+[^;'"`]*\+\s*$/.test(between)) { cur += '7' + body; bare += '7' + body; }
    else {
      if (cur !== null) groups.push([cur, bare]);
      cur = (/[\w)\]]\s*\+\s*$/.test(between) ? '7' : '') + body;
      bare = body;
    }
    end = m.index + m[0].length;
  }
  if (cur !== null && /^\s*\+\s*[\w(]/.test(line.slice(end))) cur += '7';
  if (cur !== null) groups.push([cur, bare]);
  const nodes = [];
  const clean = (n) => n.replace(/\s+/g, ' ').trim();
  for (const [withVal, plain] of groups) {
    const a = withVal.split(/<[^>]*>?/).map(clean);
    const b = plain.split(/<[^>]*>?/).map(clean);
    a.forEach((n, i) => nodes.push(b[i] !== undefined && b[i] !== n ? [n, b[i]] : [n]));
  }
  return nodes;
}

function userStrings(file) {
  const lines = fs.readFileSync(path.join(APP, file), 'utf8').split('\n');
  const out = [];
  let depth = null;
  lines.forEach((line, i) => {
    if (depth === null && UNUSED_BLOCK_START.test(line)) depth = 0;
    if (depth !== null) {
      depth += (line.match(/[{[]/g) || []).length - (line.match(/[}\]]/g) || []).length;
      if (depth <= 0 && /[}\]]/.test(line)) depth = null;
      return;
    }
    if (/^\s*(\/\/|\*)/.test(line) || /console\.|throw new Error|\blog\(|classList|querySelector|dataset\./.test(line)) return;
    for (const alts of textNodes(line)) {
      const part = alts[0];
      if (/\|\||\?\s*$|^:/.test(part)) continue; // code fragments of nested template expressions
      if (!/[A-Za-z]{2,}/.test(part) || /[{}=;]|\b(px|rgba|var\(|stroke|class=|style=|aria-|data-)\b/.test(part)) continue;
      if (/^[a-z0-9]+([-_][a-z0-9]+)+(\s+[a-z0-9]+([-_][a-z0-9]+)*)*\s*-?$/.test(part)) continue; // css class lists
      if (!/\s/.test(part) && !/^[A-Z]/.test(part)) continue; // identifiers / keys
      if (/^(PASS|WARN|CRITICAL|UNKNOWN|HEALTHY|WARNING|OFFLINE|GET|POST|PUT|DELETE|FAIL)$/.test(part)) continue;
      out.push({ where: `${file}:${i + 1}`, part, alts });
    }
  });
  return out;
}

test('every user-facing string in the JS modules has an Arabic copy', () => {
  const { pvI18n } = load('ar');
  const missing = [];
  for (const f of ['app.js', 'home.js', 'analytics.js', 'garden.js', 'settings.js', 'profile.js', 'api.js']) {
    for (const { where, part, alts } of userStrings(f)) {
      if (alts.some((a) => IGNORED.has(a) || pvI18n.isTechnical(a) || ARABIC.test(pvI18n.t(a)))) continue;
      missing.push(`${where} ${part}`);
    }
  }
  assert.deepEqual(missing, []);
});
