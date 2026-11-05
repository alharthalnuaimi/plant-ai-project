// API client and base-URL config tests, with fetch mocked. Run: node --test frontend/tests/api.test.js
// Lives outside mobile-app/ because Vercel publishes that whole folder.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const APP = path.join(__dirname, '..', 'mobile-app');
const API_SRC = fs.readFileSync(path.join(APP, 'api.js'), 'utf8');
const CONFIG_SRC = fs.readFileSync(path.join(APP, 'config.js'), 'utf8');

function storage(init = {}) {
  const m = new Map(Object.entries(init));
  return { getItem: (k) => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)) };
}

function loadConfig({ href = 'http://localhost:3000/', stored = {}, envUrl } = {}) {
  const u = new URL(href);
  const window = { location: { search: u.search, hostname: u.hostname }, __PLANT_API_URL__: envUrl };
  vm.runInNewContext(CONFIG_SRC, { window, localStorage: storage(stored), URLSearchParams });
  return window;
}

const json = (status, body) => ({ ok: status < 400, status, json: async () => body, text: async () => JSON.stringify(body) });

function loadApi(responder, windowExtra = {}) {
  const calls = [];
  const window = { PLANT_API_BASE: 'http://api.test', ...windowExtra };
  const ctx = {
    window,
    FormData,
    URLSearchParams,
    console,
    setTimeout,
    fetch: async (url, opts = {}) => {
      calls.push({ url, ...opts });
      return responder(url, opts);
    },
  };
  vm.createContext(ctx);
  vm.runInContext(API_SRC, ctx);
  return { ctx, calls };
}

const down = async () => { throw new TypeError('Failed to fetch'); };

// ---- config.js -----------------------------------------------------------

test('base URL: env.js value is the default on a deployed host', () => {
  const w = loadConfig({ href: 'https://app.vercel.app/', envUrl: 'https://prod.test/' });
  assert.equal(w.PLANT_API_BASE, 'https://prod.test');
});

for (const href of ['http://localhost:3000/', 'http://127.0.0.1:3000/']) {
  test(`base URL: ${href} defaults to the local backend, even with a production env.js`, () => {
    assert.equal(loadConfig({ href, envUrl: 'https://prod.test' }).PLANT_API_BASE, 'http://localhost:8000');
  });
}

test('base URL: a saved override still wins on localhost', () => {
  const w = loadConfig({ stored: { 'pv-api-base': 'http://192.168.1.10:8000' }, envUrl: 'https://prod.test' });
  assert.equal(w.PLANT_API_BASE, 'http://192.168.1.10:8000');
});

test('base URL: a phone on the LAN keeps the deployed default', () => {
  const w = loadConfig({ href: 'http://192.168.1.10:3000/', envUrl: 'https://prod.test' });
  assert.equal(w.PLANT_API_BASE, 'https://prod.test');
});

test('base URL: ?api= wins on localhost', () => {
  const w = loadConfig({ href: 'http://localhost:3000/?api=http://127.0.0.1:8000', envUrl: 'https://prod.test' });
  assert.equal(w.PLANT_API_BASE, 'http://127.0.0.1:8000');
});

test('base URL: stale localhost override is ignored on a deployed host', () => {
  const w = loadConfig({ href: 'https://app.vercel.app/', stored: { 'pv-api-base': 'http://localhost:8000' }, envUrl: 'https://prod.test' });
  assert.equal(w.PLANT_API_BASE, 'https://prod.test');
});

test('identity defaults are set', () => {
  const w = loadConfig();
  assert.equal(w.PLANT_USER_ID, 'demo_user');
  assert.equal(w.PLANT_ZONE_ID, 'zone_alpha');
  assert.equal(w.PLANT_DEVICE_ID, 'esp32_001');
});

// ---- /predict and /chat ---------------------------------------------------

test('predict: posts multipart with zone, device, user and source', async () => {
  const { ctx, calls } = loadApi(() => json(200, { disease: 'Rust' }));
  const out = await ctx.predictPlantImage(new Blob(['x']), { zone_id: 'z1', device_id: 'd1', user_id: 'u1', source: 'camera' });
  assert.equal(out.disease, 'Rust');
  assert.equal(calls[0].url, 'http://api.test/predict');
  assert.equal(calls[0].method, 'POST');
  assert.equal(calls[0].headers, undefined); // browser must set the multipart boundary itself
  assert.equal(calls[0].body.get('zone_id'), 'z1');
  assert.equal(calls[0].body.get('device_id'), 'd1');
  assert.equal(calls[0].body.get('user_id'), 'u1');
  assert.equal(calls[0].body.get('source'), 'camera');
});

test('predict: explicit zone beats the Garden selection', async () => {
  const { ctx, calls } = loadApi(() => json(200, {}), { plantGarden: { getSelectedZoneSlug: () => 'garden_zone' } });
  await ctx.predictPlantImage(new Blob(['x']), { zone_id: 'explicit' });
  assert.equal(calls[0].body.get('zone_id'), 'explicit');
});

for (const [name, body, expected] of [
  ['backend error field', { error: 'Expected an image upload' }, 'Expected an image upload'],
  ['validation details', { error: 'validation_error', details: [{ msg: 'field required' }] }, 'field required'],
  ['legacy detail field', { detail: 'nope' }, 'nope'],
]) {
  test(`predict: surfaces ${name}`, async () => {
    const { ctx } = loadApi(() => json(400, body));
    await assert.rejects(ctx.predictPlantImage(new Blob(['x'])), { message: expected });
  });
}

test('predict: non-JSON error falls back to the status code', async () => {
  const { ctx } = loadApi(() => ({ ok: false, status: 502, json: async () => { throw new Error('html'); } }));
  await assert.rejects(ctx.predictPlantImage(new Blob(['x'])), { message: 'HTTP 502' });
});

test('predict and chat: a missing base URL throws instead of calling fetch', async () => {
  const { ctx, calls } = loadApi(() => json(200, {}), { PLANT_API_BASE: '' });
  await assert.rejects(ctx.predictPlantImage(new Blob(['x'])), /not configured/);
  await assert.rejects(ctx.postChat({}), /not configured/);
  assert.equal(calls.length, 0);
});

test('chat: sends JSON and returns the reply', async () => {
  const { ctx, calls } = loadApi(() => json(200, { reply: 'hi' }));
  const out = await ctx.postChat({ user_question: 'q' });
  assert.equal(out.reply, 'hi');
  assert.equal(calls[0].headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(calls[0].body), { user_question: 'q' });
});

// ---- zones and devices ----------------------------------------------------

test('zones: save posts JSON and returns the saved row', async () => {
  const { ctx, calls } = loadApi(() => json(200, { slug: 'z' }));
  assert.equal((await ctx.saveZone({ slug: 'z', name: 'Z' })).slug, 'z');
  assert.equal(calls[0].url, 'http://api.test/zones');
  assert.equal(calls[0].method, 'POST');
});

test('zones: save returns null on server error or network failure, so the UI can roll back', async () => {
  assert.equal(await loadApi(() => json(500, {})).ctx.saveZone({}), null);
  assert.equal(await loadApi(down).ctx.saveZone({}), null);
});

test('zones: delete encodes the slug and reports success', async () => {
  const { ctx, calls } = loadApi(() => json(200, { ok: true }));
  assert.equal(await ctx.deleteZone('a b/c'), true);
  assert.equal(calls[0].url, 'http://api.test/zones/a%20b%2Fc');
  assert.equal(calls[0].method, 'DELETE');
  assert.equal(await loadApi(() => json(404, {})).ctx.deleteZone('x'), false);
});

test('zones: fetch failure returns ok:false with an empty list', async () => {
  const out = await loadApi(down).ctx.fetchZones();
  assert.equal(out.ok, false);
  assert.equal(out.zones.length, 0);
});

test('devices: filter by zone, and report failure', async () => {
  const { ctx, calls } = loadApi(() => json(200, { devices: [], source: 'memory' }));
  await ctx.fetchDevices('z 1');
  assert.match(calls[0].url, /\/devices\?zone=z(%20|\+)1$/);
  assert.equal((await loadApi(down).ctx.fetchDevices()).ok, false);
});

// ---- reads ----------------------------------------------------------------

test('scan history: builds the query string', async () => {
  const { ctx, calls } = loadApi(() => json(200, { scans: [] }));
  await ctx.fetchScanHistory({ zone: 'z1', status: 'CRITICAL', limit: 5 });
  const q = new URL(calls[0].url).searchParams;
  assert.equal(q.get('zone'), 'z1');
  assert.equal(q.get('status'), 'CRITICAL');
  assert.equal(q.get('limit'), '5');
});

test('reads: a non-OK response returns null', async () => {
  const { ctx } = loadApi(() => json(500, {}));
  assert.equal(await ctx.fetchAnalyticsSummary(), null);
  assert.equal(await ctx.fetchScanDetail('1'), null);
});

test('health: network failure returns ok:false', async () => {
  assert.equal((await loadApi(down).ctx.checkBackendHealth()).ok, false);
  assert.equal((await loadApi(down).ctx.fetchModelsHealth()).ok, false);
});

// ---- field names and element IDs ------------------------------------------
// These pages need a full DOM, so check the source. Backend side: test_fields_the_frontend_reads_exist.

const src = (name) => fs.readFileSync(path.join(APP, name), 'utf8');

test('profile reads resolved_weights from /models/registry', () => {
  assert.match(src('profile.js'), /reg\.data\.resolved_weights/);
  assert.doesNotMatch(src('profile.js'), /weights_path|yolo\?\.path/);
});

test('diagnostics reads zone_slug, and jobs read created_at', () => {
  assert.match(src('settings.js'), /d\.zone_slug/);
  assert.doesNotMatch(src('settings.js'), /queued_at/);
});

test('the Export action clicks a button that exists', () => {
  const target = src('app.js').match(/getElementById\('(prof-export[\w-]*)'\)\?\.click\(\)/)[1];
  assert.match(src('index.html'), new RegExp(`id="${target}"`));
});

test('a failed scan does not create a scan notification', () => {
  const observer = src('app.js').match(/const resObserver[\s\S]*?pushNotification/)[0];
  assert.match(observer, /'Scan Failed'\) return/);
});

// ---- demo mode ------------------------------------------------------------

test('demo mode: predict and chat use fixtures with no network call', async () => {
  const plantDemo = { isOn: () => true, fixtures: { predictPlantImage: () => ({ disease: 'Demo' }), postChat: () => ({ reply: 'demo' }) } };
  const { ctx, calls } = loadApi(() => json(200, {}), { plantDemo });
  assert.equal((await ctx.predictPlantImage(new Blob(['x']), { zone_id: 'z' })).zone_id, 'z');
  assert.equal((await ctx.postChat({})).reply, 'demo');
  assert.equal(calls.length, 0);
});
