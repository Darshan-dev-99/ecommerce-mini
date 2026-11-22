/** Seller fulfilment desk: filter the order book, advance statuses, inspect timelines. */

import {
  api, money, escapeHtml, statusClass, formatDateTime, timeAgo,
  toast, openModal, confirmDialog, sessionReady, session,
} from './api.js';

const STATUSES = [
  'Placed', 'Packed', 'Shipped', 'Out for delivery',
  'Delivered', 'Cancelled', 'Return requested', 'Returned',
];

const $ = (id) => document.getElementById(id);
const state = { status: 'all', q: '' };

/* --------------------------------------------------------------- rendering */

function tabHtml(status, label, counts, total) {
  const count = status === 'all' ? total : (counts[status] || 0);
  return `<button class="tab${state.status === status ? ' is-on' : ''}" type="button" data-status="${escapeHtml(status)}">
    ${escapeHtml(label)} <span style="opacity:.7">${count}</span>
  </button>`;
}

function renderTabs(counts, total) {
  $('order-tabs').innerHTML = [
    tabHtml('all', 'All', counts, total),
    ...STATUSES.map((status) => tabHtml(status, status, counts, total)),
  ].join('');
}

function rowHtml(order) {
  const next = (order.next_statuses || []).filter((status) => status !== 'Cancelled');
  return `
    <tr data-order="${order.id}">
      <td>
        <a class="link" href="/orders/${order.id}/" target="_blank" rel="noopener">${escapeHtml(order.order_number)}</a>
        <div class="small muted">${escapeHtml(order.invoice_number || '—')}</div>
      </td>
      <td>
        <b>${escapeHtml(order.customer.display_name)}</b>
        <div class="small muted">@${escapeHtml(order.customer.username)} · ${escapeHtml(order.shipping_pincode)}</div>
      </td>
      <td class="small">${order.item_count} item${order.item_count > 1 ? 's' : ''}</td>
      <td class="small muted">${timeAgo(order.created_at)}</td>
      <td class="small">${escapeHtml(order.payment_method_display)}<div class="small muted">${escapeHtml(order.payment_status)}</div></td>
      <td class="num">${money(order.total_amount)}</td>
      <td><span class="status-chip status-${statusClass(order.status)}">${escapeHtml(order.status)}</span></td>
      <td>
        <div class="table-actions">
          <button class="link-btn" type="button" data-open="${order.id}">Open</button>
          ${next.length ? `<button class="link-btn" type="button" data-advance="${order.id}" data-to="${escapeHtml(next[0])}">→ ${escapeHtml(next[0])}</button>` : ''}
        </div>
      </td>
    </tr>`;
}

let current = { results: [] };

function render(payload) {
  current = payload;
  $('orders-sub').textContent = `${payload.count} order${payload.count === 1 ? '' : 's'} shown · updated ${new Date().toLocaleTimeString('en-IN')}`;
  $('orders-count').textContent = `${payload.count} shown`;
  renderTabs(payload.status_counts || {}, Object.values(payload.status_counts || {}).reduce((a, b) => a + b, 0));

  const body = document.querySelector('#orders-table tbody');
  body.innerHTML = payload.results.length
    ? payload.results.map(rowHtml).join('')
    : '<tr><td colspan="8" class="muted">No orders match this filter.</td></tr>';
}

/* ---------------------------------------------------------------- loaders */

async function load({ toastOnLoad = false } = {}) {
  try {
    const payload = await api.orders({
      status: state.status === 'all' ? '' : state.status,
      q: state.q,
    });
    render(payload);
    if (toastOnLoad) toast('Order book refreshed.', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
}

const byId = (id) => current.results.find((order) => String(order.id) === String(id));

/* ------------------------------------------------------------- order modal */

function timelineHtml(events) {
  if (!events || !events.length) return '<p class="muted small">No tracking events yet.</p>';
  return `<div class="stack" style="gap:0">${events.map((event, index) => `
    <div style="display:flex;gap:12px;padding:10px 0;${index < events.length - 1 ? 'border-bottom:1px dashed var(--line-soft)' : ''}">
      <span class="status-chip status-${statusClass(event.status)}">${escapeHtml(event.status)}</span>
      <div style="min-width:0">
        <b style="font-size:13px">${escapeHtml(event.note || 'Status updated')}</b>
        <div class="small muted">${formatDateTime(event.created_at)}${event.location ? ` · ${escapeHtml(event.location)}` : ''}</div>
      </div>
    </div>`).join('')}</div>`;
}

function itemsHtml(order) {
  return order.items.map((item) => `
    <div class="row between" style="padding:8px 0;border-bottom:1px dashed var(--line-soft)">
      <span style="min-width:0">
        <b style="font-size:13px">${escapeHtml(item.product_name)}</b>
        <div class="small muted">${item.quantity} × ${money(item.unit_price)}${item.product_brand ? ` · ${escapeHtml(item.product_brand)}` : ''}</div>
      </span>
      <b style="font-size:13px">${money(item.line_total)}</b>
    </div>`).join('');
}

function openOrder(order) {
  const next = order.next_statuses || [];
  openModal({
    title: `Order ${order.order_number}`,
    wide: true,
    body: `
      <div class="mini-stat" style="margin-bottom:12px">
        <span>Status: <b>${escapeHtml(order.status)}</b></span>
        <span>Payment: <b>${escapeHtml(order.payment_method_display)} · ${escapeHtml(order.payment_status)}</b></span>
        <span>Placed: <b>${formatDateTime(order.created_at)}</b></span>
        <span>ETA: <b>${order.delivery_eta || '—'}</b></span>
      </div>

      <div class="grid-2" style="gap:16px">
        <div>
          <h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:6px">Items</h3>
          ${itemsHtml(order)}
          <div class="invoice-totals" style="width:100%;margin-top:10px">
            <div><span>Subtotal</span><span>${money(order.subtotal)}</span></div>
            ${Number(order.discount_amount) ? `<div><span>Coupon ${escapeHtml(order.coupon_code)}</span><span style="color:var(--green)">− ${money(order.discount_amount)}</span></div>` : ''}
            <div><span>Delivery</span><span>${Number(order.delivery_fee) ? money(order.delivery_fee) : 'FREE'}</span></div>
            ${Number(order.cod_fee) ? `<div><span>COD fee</span><span>${money(order.cod_fee)}</span></div>` : ''}
            <div><span>GST (included)</span><span>${money(order.gst_amount)}</span></div>
            <div class="grand"><span>Total</span><span>${money(order.total_amount)}</span></div>
          </div>
        </div>
        <div>
          <h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin-bottom:6px">Ship to</h3>
          <p style="font-size:13px;line-height:1.6">
            <b>${escapeHtml(order.shipping_name)}</b><br>
            ${escapeHtml(order.full_address)}<br>
            ${escapeHtml(order.shipping_pincode)} · ${escapeHtml(order.shipping_phone)}
          </p>
          <h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:14px 0 6px">Tracking timeline</h3>
          ${timelineHtml(order.events)}
          ${order.returns && order.returns.length ? `
            <h3 style="font-size:13px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted);margin:14px 0 6px">Returns</h3>
            ${order.returns.map((row) => `<div class="small">${escapeHtml(row.reason_display || row.reason)} — <b>${escapeHtml(row.status)}</b>${row.admin_note ? ` · ${escapeHtml(row.admin_note)}` : ''}</div>`).join('')}` : ''}
        </div>
      </div>

      ${next.length ? `
        <hr class="divider">
        <div class="form-grid">
          <div class="field">
            <label for="adv-status">Move to status</label>
            <select class="select" id="adv-status">
              ${next.map((status) => `<option value="${escapeHtml(status)}">${escapeHtml(status)}</option>`).join('')}
            </select>
          </div>
          <div class="field">
            <label for="adv-location">Courier hub / location</label>
            <input class="input" id="adv-location" placeholder="e.g. Mumbai sort centre">
          </div>
          <div class="field span-2">
            <label for="adv-note">Note shown to the customer</label>
            <input class="input" id="adv-note" placeholder="Optional tracking note">
          </div>
        </div>` : '<p class="inline-note" style="margin-top:14px">This order is in a final state — no further transitions.</p>'}
    `,
    footer: next.length ? `
      <button class="btn" type="button" data-close>Close</button>
      <button class="btn btn-primary" type="button" data-save>Update status</button>` : `
      <button class="btn" type="button" data-close>Close</button>`,
    onMount(el, close) {
      el.querySelector('[data-close]')?.addEventListener('click', close);
      el.querySelector('[data-save]')?.addEventListener('click', async () => {
        const button = el.querySelector('[data-save]');
        button.disabled = true;
        try {
          const result = await api.setOrderStatus(order.id, {
            status: el.querySelector('#adv-status').value,
            location: el.querySelector('#adv-location').value,
            note: el.querySelector('#adv-note').value,
          });
          toast(result.message, 'success');
          close();
          await load();
        } catch (error) {
          toast(error.message, 'error');
          button.disabled = false;
        }
      });
    },
  });
}

/* ------------------------------------------------------------------- boot */

$('order-tabs').addEventListener('click', (event) => {
  const tab = event.target.closest('[data-status]');
  if (!tab) return;
  state.status = tab.dataset.status;
  load();
});

$('orders-table').addEventListener('click', async (event) => {
  const open = event.target.closest('[data-open]');
  if (open) {
    const order = byId(open.dataset.open);
    if (order) openOrder(order);
    return;
  }

  const advance = event.target.closest('[data-advance]');
  if (advance) {
    const order = byId(advance.dataset.advance);
    const target = advance.dataset.to;
    if (!order) return;
    const ok = await confirmDialog({
      title: `Move ${order.order_number} to ${target}?`,
      message: 'The customer sees this change live on their tracking page.',
      confirmLabel: `Mark ${target}`,
    });
    if (!ok) return;
    try {
      const result = await api.setOrderStatus(order.id, { status: target });
      toast(result.message, 'success');
      await load();
    } catch (error) {
      toast(error.message, 'error');
    }
  }
});

$('order-search-form').addEventListener('submit', (event) => {
  event.preventDefault();
  state.q = $('order-search').value.trim();
  load();
});

$('orders-refresh').addEventListener('click', () => load({ toastOnLoad: true }));

await sessionReady;
if (!session.authenticated) {
  location.assign(`/login/?next=${encodeURIComponent(location.pathname)}`);
} else if (!session.user.is_store_admin) {
  location.assign('/');
} else {
  await load();
  setInterval(() => load(), 30000);
}
