// English/Arabic i18n engine tests. Run: node --test frontend/tests/
// The DOM translation itself is verified in a real browser; these tests
// cover the engine, persistence, direction, backend URLs and dictionary coverage.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP = path.join(__dirname, '..', 'mobile-app');
const DICT_SRC = fs.readFileSync(path.join(APP, 'i18n-ar.js'), 'utf8');
const I18N_SRC = fs.readFileSync(path.join(APP, 'i18n.js'), 'utf8');
const ARABIC = /[؀-ۿ]/;

function storage(init = {}) {
  const m = new Map(Object.entries(init));
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), _m: m };
}

function load({ stored = {}, apiBase = 'http://api.test' } = {}) {
  const attrs = {};
  const documentElement = {
    setAttribute: (k, v) => { attrs[k] = v; },
    getAttribute: (k) => attrs[k],
  };
  const document = {
    documentElement,
    readyState: 'loading',
    title: 'PlantVision AI — Plant Disease Detection Dashboard',
    addEventListener() {},
    dispatchEvent() {},
    querySelectorAll: () => [],
  };
  const fetchCalls = [];
  const window = {
    PLANT_API_BASE: apiBase,
    fetch: (url, init) => { fetchCalls.push(String(url)); return Promise.resolve({ ok: true }); },
    addEventListener() {},
    dispatchEvent() {},
  };
  const localStorage = storage(stored);
  const ctx = { window, document, localStorage, URL, CustomEvent: function (n, o) { this.type = n; this.detail = o && o.detail; } };
  vm.runInNewContext(DICT_SRC, ctx);
  vm.runInNewContext(I18N_SRC, ctx);
  return { i18n: window.pvI18n, window, attrs, localStorage, document, fetchCalls };
}

test('defaults to English and left-to-right when nothing is stored', () => {
  const { i18n, attrs } = load();
  assert.equal(i18n.getLang(), 'en');
  assert.equal(attrs.lang, 'en');
  assert.equal(attrs.dir, 'ltr');
});

test('restores the stored language on load', () => {
  const { i18n, attrs } = load({ stored: { 'pv-lang': 'ar' } });
  assert.equal(i18n.getLang(), 'ar');
  assert.equal(attrs.lang, 'ar');
  assert.equal(attrs.dir, 'rtl');
});

test('setLang persists the choice and flips direction both ways', () => {
  const { i18n, attrs, localStorage } = load();
  i18n.setLang('ar');
  assert.equal(localStorage.getItem('pv-lang'), 'ar');
  assert.equal(attrs.dir, 'rtl');
  i18n.setLang('en');
  assert.equal(localStorage.getItem('pv-lang'), 'en');
  assert.equal(attrs.dir, 'ltr');
  assert.equal(attrs.lang, 'en');
});

test('unknown languages fall back to English', () => {
  const { i18n } = load({ stored: { 'pv-lang': 'fr' } });
  assert.equal(i18n.getLang(), 'en');
});

test('t() is the identity in English and translates in Arabic', () => {
  const { i18n } = load();
  assert.equal(i18n.t('Scan Log'), 'Scan Log');
  i18n.setLang('ar');
  assert.match(i18n.t('Scan Log'), ARABIC);
  assert.equal(i18n.t('zone_alpha'), 'zone_alpha'); // identifiers stay
});

test('t() keeps surrounding whitespace and handles dynamic templates', () => {
  const { i18n } = load({ stored: { 'pv-lang': 'ar' } });
  const out = i18n.t('  Scan Log ');
  assert.ok(out.startsWith('  ') && out.endsWith(' '));
  const upd = i18n.t('Updated 10:32');
  assert.match(upd, ARABIC);
  assert.ok(upd.includes('10:32'));
  const ago = i18n.t('5m ago');
  assert.match(ago, ARABIC);
  assert.ok(ago.includes('5'));
});

test('t() substitutes {name} placeholders', () => {
  const { i18n } = load();
  assert.equal(i18n.t('{n} scans', { n: 3 }), '3 scans');
  i18n.setLang('ar');
  assert.ok(i18n.t('{n} scans', { n: 3 }).includes('3'));
});

test('every Arabic entry is non-empty Arabic text', () => {
  const { window } = load();
  const bad = Object.entries(window.PV_AR.exact).filter(([, v]) => typeof v !== 'string' || !ARABIC.test(v));
  assert.deepEqual(bad, []);
});

test('every static string in index.html has an Arabic copy', () => {
  const { i18n } = load({ stored: { 'pv-lang': 'ar' } });
  const html = fs.readFileSync(path.join(APP, 'index.html'), 'utf8')
    .replace(/<!--[\s\S]*?-->/g, '').replace(/<script[\s\S]*?<\/script>/g, '')
    .replace(/<svg[\s\S]*?<\/svg>/g, '').replace(/<head>[\s\S]*?<\/head>/, '')
    .replace(/<[^>]*data-i18n-skip[^>]*>[^<]*/g, '');
  const decode = (s) => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
  const strings = new Set();
  for (const m of html.matchAll(/>([^<>]+)</g)) {
    const s = decode(m[1].replace(/\s+/g, ' ').trim());
    if (/[A-Za-z]{2,}/.test(s)) strings.add(s);
  }
  for (const m of html.matchAll(/\b(title|placeholder|aria-label|data-tip|alt)="([^"]+)"/g)) {
    if (/[A-Za-z]{2,}/.test(m[2])) strings.add(decode(m[2]));
  }
  const untranslated = [...strings].filter((s) => !i18n.isTechnical(s) && !ARABIC.test(i18n.t(s)));
  assert.deepEqual(untranslated, []);
});

test('backend URLs get lang=ar only in Arabic and never for sensor routes', () => {
  const { i18n } = load();
  assert.equal(i18n.withLang('http://api.test/report'), 'http://api.test/report');
  i18n.setLang('ar');
  assert.equal(i18n.withLang('http://api.test/report'), 'http://api.test/report?lang=ar');
  assert.equal(i18n.withLang('http://api.test/scans/history?limit=5'), 'http://api.test/scans/history?limit=5&lang=ar');
  assert.equal(i18n.withLang('http://api.test/sensor/latest'), 'http://api.test/sensor/latest');
  assert.equal(i18n.withLang('https://tiles.example/x.png'), 'https://tiles.example/x.png');
});

test('fetch to the backend carries lang=ar in Arabic', async () => {
  const { i18n, window, fetchCalls } = load({ stored: { 'pv-lang': 'ar' } });
  await window.fetch('http://api.test/analytics/insights');
  await window.fetch('http://api.test/sensor/latest');
  assert.deepEqual(fetchCalls, ['http://api.test/analytics/insights?lang=ar', 'http://api.test/sensor/latest']);
  i18n.setLang('en');
  await window.fetch('http://api.test/analytics/insights');
  assert.equal(fetchCalls[2], 'http://api.test/analytics/insights');
});

test('locale() keeps Latin digits for Arabic', () => {
  const { i18n } = load({ stored: { 'pv-lang': 'ar' } });
  assert.equal(i18n.locale(), 'ar-u-nu-latn');
});
