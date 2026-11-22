/** Order history: status tabs, cancellation, returns, invoices, buy again. */

import {
  api, money, escapeHtml, toast, openModal, confirmDialog, statusClass, formatDate,
  refreshCartCount,
} from './api.js';

const tabsHost = document.getElementById('order-tabs');
const listHost = document.getElementById('order-list');

const STATUSES = [
  'Placed', 'Packed', 'Shipped', 'Out for delivery', 'Delivered',
  'Return requested', 'Returned', 'Cancelled',
];

const state = { status: 'all', q: '', orders: [], counts: {}, timer: null };

const REASONS = [
  ['Damaged', 'Item arrived damaged'],
  ['Wrong item', 'Wrong item delivered'],
  ['Not as described', 'Not as described'],
  ['Changed mind', 'Changed my mind'],
  ['Other', 'Other'],
];

function tabsHtml() {
  const all = Object.values(state.counts).reduce((sum, value) => sum + value, 0);
  const entries = [['all', 'All', all], ...STATUSES.map((status) => [status, status, state.counts[status] || 0])];
  return entries.map(([value, label, count]) => `
    <button class="tab ${state.status === value ? 'is-on' : ''}" type="button" role="tab" data-status="${value}">
      ${escapeHtml(label)}${count ? ` <span class="muted" style="font-weight:600">(${count})</span>` : ''}
    </button>`).join('');
}

function orderHtml(order) {
  const items = order.items.slice(0, 2);
  const more = order.items.length - items.length;
  const cancelled = order.status === 'Cancelled' || order.status === 'Returned';
  const eta = order.delivery_eta
    ? new Date(order.delivery_eta).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })
    : '';

  return `
    <article class="order-card" data-order="${order.id}">
      <div class="order-top">
        <span class="num">${escapeHtml(order.order_number)}</span>
        <span class="meta">Placed ${formatDate(order.created_at)}</span>
        <span class="meta">· ${order.item_count} item${order.item_count === 1 ? '' : 's'}</span>
        <span class="meta">· ${money(order.total_amount)}</span>
        <div class="right">
          <span class="status-chip status-${statusClass(order.status)}">${escapeHtml(order.status)}</span>
          <a class="link-btn" href="/orders/${order.id}/">View details ›</a>
        </div>
      </div>
      <div class="order-body">
        <div class="order-items">
          ${items.map((item) => `
            <div class="order-line">
              <img src="${escapeHtml(item.image_url || '')}" alt="">
              <div class="grow">
                <b>${escapeHtml(item.product_name)}</b>
                <span>Qty ${item.quantity} · ${money(item.unit_price)}</span>
                ${item.slug ? `<a class="link small" href="/p/${encodeURIComponent(item.slug)}/">View product</a>` : ''}
              </div>
            </div>`).join('')}
          ${more > 0 ? `<span class="muted small">+ ${more} more item${more === 1 ? '' : 's'}</span>` : ''}
        </div>
        <div class="order-side">
          <div><span class="label">${cancelled ? 'Status' : 'Arriving by'}</span>
            <b>${cancelled ? escapeHtml(order.status) : eta}</b></div>
          <div><span class="label">Payment</span>
            <b>${escapeHtml(order.payment_method_display)} · ${escapeHtml(order.payment_status)}</b></div>
          <div><span class="label">Deliver to</span>
            <b>${escapeHtml(order.shipping_name)}</b>
            <span class="muted small">${escapeHtml(order.shipping_city || '')} ${order.shipping_pincode}</span></div>
          <div class="pill-row" style="margin-top:4px">
            <a class="btn btn-sm btn-outline" href="/api/orders/${order.id}/invoice/" target="_blank" rel="noopener">Invoice</a>
            ${order.is_cancellable ? `<button class="btn btn-sm btn-danger" type="button" data-cancel="${order.id}">Cancel</button>` : ''}
            ${order.is_returnable ? `<button class="btn btn-sm btn-outline" type="button" data-return="${order.id}">Return</button>` : ''}
            ${order.status === 'Delivered' || order.status === 'Returned'
              ? `<button class="btn btn-sm" type="button" data-again="${order.id}">Buy again</button>` : ''}
          </div>
        </div>
      </div>
    </article>`;
}

async function load({ silent = false } = {}) {
  if (!silent) {
    listHost.innerHTML = `<div class="card pad section-gap"><div class="skeleton sk-line" style="width:35%"></div>
      <div class="skeleton sk-line"></div></div>`;
  }
  try {
    const data = await api.orders({ status: state.status === 'all' ? '' : state.status, q: state.q });
    state.orders = data.results;
    state.counts = data.status_counts;
    tabsHost.innerHTML = tabsHtml();
    listHost.innerHTML = data.results.length
      ? data.results.map(orderHtml).join('')
      : `<div class="card empty section-gap"><span class="ico">📦</span><h2>No orders here yet</h2>
           <p>${state.status === 'all'
             ? 'When you place an order you can track it live from this page.'
             : `You have no orders with status “${escapeHtml(state.status)}”.`}</p>
           <a class="btn btn-cart" href="/shop/">Start shopping</a></div>`;
    document.getElementById('orders-sub').textContent =
      `${data.results.length} order${data.results.length === 1 ? '' : 's'} · live status updates every few seconds`;
    schedulePoll();
  } catch (error) {
    if (silent) return;
    listHost.innerHTML = `<div class="card empty"><h2>Could not load orders</h2><p>${escapeHtml(error.message)}</p></div>`;
  }
}

function schedulePoll() {
  clearTimeout(state.timer);
  const active = state.orders.some((order) => !['Delivered', 'Cancelled', 'Returned'].includes(order.status));
  if (active) state.timer = setTimeout(() => load({ silent: true }), 20000);
}

/* --------------------------------------------------------------- actions */

async function cancelOrder(id) {
  const order = state.orders.find((row) => row.id === id);
  const okay = await confirmDialog({
    title: `Cancel ${order ? order.order_number : 'order'}?`,
    message: order && order.payment_status === 'Paid'
      ? 'Your payment will be refunded to the original method within 3–5 business days.'
      : 'Stock will be released back to the catalogue immediately.',
    confirmLabel: 'Cancel order',
    danger: true,
  });
  if (!okay) return;
  try {
    const data = await api.cancelOrder(id, 'Changed mind');
    toast(data.message, 'success');
    load({ silent: true });
  } catch (error) {
    toast(error.message, 'error');
  }
}

function returnOrder(id) {
  const order = state.orders.find((row) => row.id === id);
  openModal({
    title: 'Request a return',
    body: `
      <p class="muted small" style="margin-bottom:14px">Order ${escapeHtml(order.order_number)} · refund to ${escapeHtml(order.payment_method_display)}</p>
      <form id="return-form">
        <div class="field"><label>Reason</label>
          <select name="reason">${REASONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select></div>
        <div class="field"><label>Tell us more (optional)</label>
          <textarea name="comment" maxlength="1000" placeholder="What went wrong?"></textarea></div>
        <div class="form-actions"><button class="btn btn-primary" type="submit">Submit return request</button></div>
      </form>`,
    onMount(el, close) {
      el.querySelector('#return-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const form = new FormData(event.target);
        try {
          const data = await api.returnOrder(id, Object.fromEntries(form.entries()));
          toast(data.message, 'success');
          close();
          load({ silent: true });
        } catch (error) {
          toast(error.message, 'error');
        }
      });
    },
  });
}

async function buyAgain(id) {
  const order = state.orders.find((row) => row.id === id);
  if (!order) return;
  let added = 0;
  for (const item of order.items) {
    try {
      await api.addToCart(item.product, item.quantity);
      added += 1;
    } catch { /* product may be discontinued */ }
  }
  await refreshCartCount();
  if (added) {
    toast(`${added} item${added === 1 ? '' : 's'} added back to your cart.`, 'success');
  } else {
    toast('Those products are no longer available.', 'error');
  }
}

/* ------------------------------------------------------------- listeners */

tabsHost.addEventListener('click', (event) => {
  const tab = event.target.closest('[data-status]');
  if (!tab) return;
  state.status = tab.dataset.status;
  load();
});

document.getElementById('order-search-form').addEventListener('submit', (event) => {
  event.preventDefault();
  state.q = document.getElementById('order-search').value.trim();
  load();
});

listHost.addEventListener('click', (event) => {
  const cancel = event.target.closest('[data-cancel]');
  if (cancel) { cancelOrder(Number(cancel.dataset.cancel)); return; }
  const ret = event.target.closest('[data-return]');
  if (ret) { returnOrder(Number(ret.dataset.return)); return; }
  const again = event.target.closest('[data-again]');
  if (again) { buyAgain(Number(again.dataset.again)); }
});

load();
