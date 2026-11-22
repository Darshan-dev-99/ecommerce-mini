/** Coupon desk: create, edit, pause and retire promotional codes. */

import {
  api, money, escapeHtml, formatDate,
  toast, openModal, confirmDialog, sessionReady, session,
} from './api.js';

const $ = (id) => document.getElementById(id);
let coupons = [];

function fieldError(error) {
  const data = error.data;
  if (!data || typeof data !== 'object') return error.message;
  if (data.detail) return Array.isArray(data.detail) ? data.detail[0] : String(data.detail);
  const key = Object.keys(data)[0];
  if (!key) return error.message;
  const value = data[key];
  return `${key.replace(/_/g, ' ')}: ${Array.isArray(value) ? value[0] : value}`;
}

const isoDay = (iso) => (iso ? String(iso).slice(0, 10) : '');
const toIso = (day, endOfDay = false) => (day ? `${day}T${endOfDay ? '23:59:59' : '00:00:00'}+05:30` : null);

function offerText(coupon) {
  const value = Number(coupon.value);
  return coupon.discount_type === 'percent'
    ? `${value}% off${Number(coupon.max_discount) > 0 ? ` up to ${money(coupon.max_discount)}` : ''}`
    : `${money(value)} off`;
}

function rowHtml(coupon) {
  const live = coupon.is_live;
  const expired = coupon.valid_to && new Date(coupon.valid_to) < new Date();
  return `
    <tr data-coupon="${coupon.id}" style="${coupon.is_active ? '' : 'opacity:.6'}">
      <td>
        <span class="copy-code">${escapeHtml(coupon.code)}</span>
        <div class="small muted">${coupon.per_user_limit} per customer</div>
      </td>
      <td>
        <b style="font-size:13px">${escapeHtml(offerText(coupon))}</b>
        <div class="small muted">${escapeHtml(coupon.description || '—')}</div>
      </td>
      <td class="num small">${coupon.discount_type === 'percent' ? `${Number(coupon.value)}%` : money(coupon.value)}</td>
      <td class="num small">${money(coupon.min_order_value)}</td>
      <td class="small muted">
        ${formatDate(coupon.valid_from)} → ${coupon.valid_to ? formatDate(coupon.valid_to) : 'no end'}
        ${expired ? '<div style="color:var(--red)">expired</div>' : ''}
      </td>
      <td class="num small">
        ${coupon.used_count}${coupon.usage_limit ? ` / ${coupon.usage_limit}` : ''}
      </td>
      <td>
        <button class="status-chip ${live ? 'status-Delivered' : 'status-Cancelled'}" type="button" data-toggle="${coupon.id}">
          ${live ? 'Live' : coupon.is_active ? 'Scheduled / capped' : 'Paused'}
        </button>
      </td>
      <td>
        <div class="table-actions">
          <button class="link-btn" type="button" data-edit="${coupon.id}">Edit</button>
          <button class="link-btn danger" type="button" data-delete="${coupon.id}">Delete</button>
        </div>
      </td>
    </tr>`;
}

function render() {
  $('coupons-sub').textContent =
    `${coupons.length} coupon${coupons.length === 1 ? '' : 's'} · ${coupons.filter((row) => row.is_live).length} live right now`;
  document.querySelector('#coupons-table tbody').innerHTML = coupons.length
    ? coupons.map(rowHtml).join('')
    : '<tr><td colspan="8" class="muted">No coupons yet — create the first one.</td></tr>';
}

async function load() {
  try {
    coupons = await api.coupons();
    if (!Array.isArray(coupons)) coupons = coupons.results || [];
    render();
  } catch (error) {
    toast(error.message, 'error');
  }
}

/* ------------------------------------------------------------------ editor */

function formHtml(coupon = {}) {
  const value = (key, fallback = '') => escapeHtml(coupon[key] ?? fallback);
  const type = coupon.discount_type || 'percent';
  return `
    <form id="coupon-form" novalidate>
      <div class="form-grid">
        <div class="field">
          <label for="cf-code">Coupon code *</label>
          <input class="input" id="cf-code" value="${value('code')}" maxlength="24" style="text-transform:uppercase" required>
          <span class="hint">Letters and numbers only. Shoppers type this in the cart.</span>
        </div>
        <div class="field">
          <label for="cf-type">Discount type *</label>
          <select class="select" id="cf-type">
            <option value="percent"${type === 'percent' ? ' selected' : ''}>Percentage off</option>
            <option value="flat"${type === 'flat' ? ' selected' : ''}>Flat amount off</option>
          </select>
        </div>
        <div class="field">
          <label for="cf-value">Value *</label>
          <input class="input" id="cf-value" type="number" min="1" step="1" value="${value('value')}" required>
        </div>
        <div class="field">
          <label for="cf-max">Max discount cap (₹)</label>
          <input class="input" id="cf-max" type="number" min="0" step="1" value="${value('max_discount')}">
        </div>
        <div class="field">
          <label for="cf-min">Minimum order value (₹)</label>
          <input class="input" id="cf-min" type="number" min="0" step="1" value="${value('min_order_value', 0)}">
        </div>
        <div class="field">
          <label for="cf-usage">Total usage limit</label>
          <input class="input" id="cf-usage" type="number" min="0" step="1" value="${value('usage_limit', 0)}">
          <span class="hint">0 means unlimited.</span>
        </div>
        <div class="field">
          <label for="cf-peruser">Per customer limit</label>
          <input class="input" id="cf-peruser" type="number" min="1" step="1" value="${value('per_user_limit', 1)}">
        </div>
        <div class="field">
          <label for="cf-to">Valid until</label>
          <input class="input" id="cf-to" type="date" value="${isoDay(coupon.valid_to)}">
        </div>
      </div>
      <div class="field">
        <label for="cf-desc">Description shown to shoppers</label>
        <input class="input" id="cf-desc" value="${value('description')}" maxlength="200"
               placeholder="Flat ₹200 off your first order above ₹999">
      </div>
      <label class="chip"><input type="checkbox" id="cf-active" ${coupon.is_active === false ? '' : 'checked'}> Active</label>
    </form>`;
}

function readForm() {
  const body = {
    code: $('cf-code').value.trim().toUpperCase(),
    discount_type: $('cf-type').value,
    value: $('cf-value').value,
    max_discount: $('cf-max').value ? $('cf-max').value : null,
    min_order_value: $('cf-min').value || 0,
    usage_limit: Number($('cf-usage').value || 0),
    per_user_limit: Number($('cf-peruser').value || 1),
    description: $('cf-desc').value.trim(),
    is_active: $('cf-active').checked,
  };
  if (!body.code) throw new Error('Give the coupon a code.');
  if (!(Number(body.value) > 0)) throw new Error('The discount value must be greater than zero.');
  if (body.discount_type === 'percent' && Number(body.value) > 90) {
    throw new Error('A percentage coupon above 90% is probably a mistake.');
  }
  if ($('cf-to').value) body.valid_to = toIso($('cf-to').value, true);
  return body;
}

function openEditor(coupon = null) {
  openModal({
    title: coupon ? `Edit ${coupon.code}` : 'Create a coupon',
    wide: true,
    body: formHtml(coupon || {}),
    footer: `
      <button class="btn" type="button" data-cancel>Cancel</button>
      <button class="btn btn-primary" type="button" data-save>${coupon ? 'Save changes' : 'Create coupon'}</button>`,
    onMount(el, close) {
      el.querySelector('[data-cancel]').addEventListener('click', close);
      el.querySelector('[data-save]').addEventListener('click', async (event) => {
        const button = event.currentTarget;
        let body;
        try {
          body = readForm();
        } catch (error) {
          toast(error.message, 'error');
          return;
        }
        button.disabled = true;
        try {
          if (coupon) {
            await api.updateCoupon(coupon.id, body);
            toast(`${body.code} updated.`, 'success');
          } else {
            await api.createCoupon(body);
            toast(`${body.code} is live on the offers page.`, 'success');
          }
          close();
          await load();
        } catch (error) {
          toast(fieldError(error), 'error');
          button.disabled = false;
        }
      });
    },
  });
}

/* ------------------------------------------------------------------- wires */

$('coupons-table').addEventListener('click', async (event) => {
  const toggle = event.target.closest('[data-toggle]');
  const edit = event.target.closest('[data-edit]');
  const remove = event.target.closest('[data-delete]');

  if (toggle) {
    const coupon = coupons.find((row) => row.id === Number(toggle.dataset.toggle));
    if (!coupon) return;
    try {
      await api.updateCoupon(coupon.id, { is_active: !coupon.is_active });
      toast(`${coupon.code} ${coupon.is_active ? 'paused' : 'resumed'}.`, 'success');
      await load();
    } catch (error) {
      toast(fieldError(error), 'error');
    }
    return;
  }

  if (edit) {
    const coupon = coupons.find((row) => row.id === Number(edit.dataset.edit));
    if (coupon) openEditor(coupon);
    return;
  }

  if (remove) {
    const coupon = coupons.find((row) => row.id === Number(remove.dataset.delete));
    if (!coupon) return;
    const ok = await confirmDialog({
      title: `Delete ${coupon.code}?`,
      message: 'If the coupon was already used by past orders it will be deactivated instead of deleted.',
      confirmLabel: 'Delete coupon',
      danger: true,
    });
    if (!ok) return;
    try {
      const result = await api.deleteCoupon(coupon.id);
      toast(result.message, 'success');
      await load();
    } catch (error) {
      toast(error.message, 'error');
    }
  }
});

$('add-coupon').addEventListener('click', () => openEditor());

/* -------------------------------------------------------------------- boot */

await sessionReady;
if (!session.authenticated) {
  location.assign(`/login/?next=${encodeURIComponent(location.pathname)}`);
} else if (!session.user.is_store_admin) {
  location.assign('/');
} else {
  await load();
}
