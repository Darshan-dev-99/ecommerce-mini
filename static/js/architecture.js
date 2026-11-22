/**
 * Architecture page: the diagram above is a picture of this file.
 *
 * `loadStats()` reads the real cache telemetry, `runSimulation()` makes the
 * backend execute the exact hop sequence (cache.get -> miss -> DB -> cache.set)
 * and reports the measured milliseconds for each one.
 */

import { api, escapeHtml, toast } from './api.js';

const TTL_LABELS = {
  product_list: ['Product grid', 'Any product / stock write'],
  product_detail: ['Product detail', 'Any product write'],
  categories: ['Categories', 'Category write'],
  brands: ['Brands', 'Brand write'],
  home: ['Home feed', 'Product or category write'],
  dashboard: ['Admin dashboard', 'Order or product write'],
  suggest: ['Search suggestions', 'Product write'],
};

const tiles = document.getElementById('stat-tiles');
const layers = document.getElementById('layers');
const ttlBody = document.querySelector('#ttl-table tbody');
const badges = document.getElementById('arch-badges');
const flow = document.getElementById('flow');
const simBtn = document.getElementById('sim-run');
const stamp = document.getElementById('live-stamp');
const hCache = document.getElementById('h-cache');
const hDb = document.getElementById('h-db');

let stats = null;
let timer = null;

/* ------------------------------------------------------------------ render */

function tile(label, value, note = '') {
  return `
    <div class="stat-tile">
      <div class="label">${escapeHtml(label)}</div>
      <div class="value">${value}${note ? ` <small>${escapeHtml(note)}</small>` : ''}</div>
    </div>`;
}

function paintStats(data) {
  stats = data;
  tiles.innerHTML = [
    tile('Hit rate', `${data.hit_rate}<small>%</small>`, ''),
    tile('Hits', data.hits.toLocaleString('en-IN'), `of ${data.requests.toLocaleString('en-IN')}`),
    tile('Misses', data.misses.toLocaleString('en-IN'), ''),
    tile('Keys', data.keys.toLocaleString('en-IN'), `v${data.catalog_version}`),
  ].join('');

  if (badges) {
    const chips = badges.querySelectorAll('span');
    if (chips[2]) chips[2].textContent = `${data.backend} · versioned keys`;
    if (chips[3]) chips[3].textContent = `${data.database} · source of truth`;
  }

  layers.innerHTML = (data.layers || []).map((layer, index) => `
    <div class="mini-stat" style="justify-content:space-between;align-items:center;border-bottom:1px solid var(--line-soft);padding-bottom:8px">
      <span><b>${escapeHtml(layer.label)}</b><br><span class="inline-note">${escapeHtml(layer.detail)}</span></span>
      <span class="live-chip${layer.live ? '' : ' off'}"><i></i>${index + 1}</span>
    </div>`).join('');

  const rows = Object.entries(data.ttls || {}).map(([key, ttl]) => {
    const [label, invalidated] = TTL_LABELS[key] || [key, 'Catalog write'];
    return `<tr><td>${escapeHtml(label)}<br><span class="inline-note">${escapeHtml(key)}</span></td>
      <td class="num">${ttl} s</td><td>${escapeHtml(invalidated)}</td></tr>`;
  });
  ttlBody.innerHTML = rows.length
    ? rows.join('')
    : '<tr><td colspan="3" class="muted">No TTLs configured.</td></tr>';

  stamp.classList.remove('off');
  stamp.lastChild.textContent = data.is_redis ? ' Redis' : ' In-process';
}

function paintStep(step, index) {
  const state = step.state === 'hit' ? 'is-hit'
    : step.state === 'miss' ? 'is-miss'
      : step.state === 'skipped' ? 'is-skip' : '';
  const ms = step.ms > 0 ? `${step.ms.toFixed(2)} ms` : '—';
  return `
    <div class="flow-step ${state}">
      <span class="flow-ico">${index + 1}</span>
      <div class="flow-body">
        <b>${escapeHtml(step.label)}</b>
        <span class="inline-note mono">${escapeHtml(step.detail || '')}</span>
      </div>
      <span class="flow-ms">${ms}</span>
    </div>`;
}

/* ------------------------------------------------------------------- actions */

async function loadStats({ quiet = true } = {}) {
  try {
    paintStats(await api.cacheStats());
  } catch (error) {
    stamp.classList.add('off');
    if (!quiet) toast(error.message, 'error');
  }
}

async function runSimulation() {
  simBtn.disabled = true;
  const original = simBtn.textContent;
  simBtn.textContent = 'Running…';
  try {
    const result = await api.simulate('flow');
    flow.innerHTML = result.steps.map(paintStep).join('') + `
      <div class="flow-step is-skip">
        <span class="flow-ico">Σ</span>
        <div class="flow-body">
          <b>${result.hit ? 'Served from cache — zero database work' : 'Served from PostgreSQL and cached'}</b>
          <span class="inline-note mono">${escapeHtml(result.key)}</span>
        </div>
        <span class="flow-ms">${result.total_ms.toFixed(2)} ms</span>
      </div>`;
    paintStats(result.stats);
    toast(result.hit
      ? 'Cache HIT — the API never touched PostgreSQL.'
      : 'Cache MISS — PostgreSQL answered and the cache was filled. Click again for a HIT.', 'info');
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    simBtn.disabled = false;
    simBtn.textContent = original;
  }
}

async function warmCache() {
  try {
    const result = await api.warmCache();
    toast(result.message, 'success');
    await loadStats({ quiet: false });
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function resetCache() {
  try {
    const result = await api.resetCache();
    toast(`${result.message} Now v${result.catalog_version}.`, 'success');
    await loadStats({ quiet: false });
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function healthCheck() {
  hCache.textContent = '…';
  hDb.textContent = '…';
  try {
    const result = await api.health();
    hCache.textContent = `${result.cache.backend} · ${result.cache.ok ? 'reachable' : 'down'} · ${result.cache.latency_ms} ms`;
    hDb.textContent = `${result.database.backend} · ${result.database.ok ? 'reachable' : 'down'} · ${result.database.latency_ms} ms`;
    toast(`Stack is ${result.status}.`, result.status === 'ok' ? 'success' : 'error');
  } catch (error) {
    hCache.textContent = 'unreachable';
    hDb.textContent = 'unreachable';
    toast(error.message, 'error');
  }
}

/* ---------------------------------------------------------------------- boot */

document.getElementById('sim-run').addEventListener('click', runSimulation);
document.getElementById('warm').addEventListener('click', warmCache);
document.getElementById('reset').addEventListener('click', resetCache);
document.getElementById('health').addEventListener('click', healthCheck);

loadStats({ quiet: false });
healthCheck();

timer = setInterval(() => {
  if (document.visibilityState === 'visible') loadStats();
}, 10000);

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') loadStats();
  clearInterval(timer);
  timer = setInterval(() => {
    if (document.visibilityState === 'visible') loadStats();
  }, 10000);
  if (stats) stamp.classList.remove('off');
});
