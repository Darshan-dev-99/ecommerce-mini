/** Order tracking: live Server-Sent Events, timeline, invoice, cancel/return. */

import {
  api, money, escapeHtml, toast, openModal, confirmDialog, statusClass,
  formatDate, formatDateTime,
} from './api.js';

const root = document.getElementById('order-root');
const orderId = window.ORDER_ID;

const STEPS = ['Placed', 'Packed', 'Shipped', 'Out for delivery', 'Delivered'];
const REASONS = [
  ['Damaged', 'Item arrived damaged'],
  ['Wrong item', 'Wrong item delivered'],
  ['Not as described', 'Not as described'],
  ['Changed mind', 'Changed my mind'],
  ['Other', 'Other'],
];

let order = null;
let stream = null;
let pollTimer = null;

/* ---------------------------------------------------------------- timeline */

function timelineHtml(current) {
  if (['Cancelled', 'Returned', 'Return requested'].includes(current.status)) {
    const events = current.events.slice().reverse();
    return `
      <div class="track">
        ${events.map((event, index) => `
          <div class="track-step ${index === 0 ? 'is-now' : 'is-done'}">
            <div class="track-dot"><i>${index === 0 ? '●' : '✓'}</i></div>
            <div class="track-copy">
              <b>${escapeHtml(event.status)}</b>
              <span>${escapeHtml(event.note || '')}${event.location ? ` · ${escapeHtml(event.location)}` : ''}</span>
              <span>${formatDateTime(event.created_at)}</span>
            </div>
          </div>`).join('')}
      </div>`;
  }

  const byStatus = {};
  current.events.forEach((event) => { byStatus[event.status] = event; });
  const reached = STEPS.indexOf(current.status);
  return `
    <div class="track">
      ${STEPS.map((step, index) => {
        const event = byStatus[step];
        const done = index < reached || (index === reached && current.status === 'Delivered');
        const now = index === reached && current.status !== 'Delivered';
        return `
          <div class="track-step ${done ? 'is-done' : ''} ${now ? 'is-now' : ''}">
            <div class="track-dot"><i>${done ? '✓' : (now ? '●' : '')}</i></div>
            <div class="track-copy">
              <b>${step}</b>
              <span>${done || now
                ? `${formatDateTime(event ? event.created_at : current.updated_at)}${event && event.location ? ` · ${escapeHtml(event.location)}` : ''}`
                : 'Pending'}</span>
              ${event && event.note ? `<span>${escapeHtml(event.note)}</span>` : ''}
            </div>
          </div>`;
      }).join('')}
    </div>`;
}

/* ------------------------------------------------------------------ render */

function render() {
  const hero = `
    <div class="order-hero">
      <div>
        <h1>${escapeHtml(order.status_display)}</h1>
        <p>${escapeHtml(order.status === 'Delivered'
          ? `Delivered on ${formatDate(order.delivered_at)}`
          : `Arriving by ${formatDate(order.delivery_eta)}`)} · Order ${escapeHtml(order.order_number)}</p>
      </div>
      <div class="pill-row">
        <span class="live-chip ${['Delivered', 'Cancelled', 'Returned'].includes(order.status) ? 'off' : ''}" id="live-chip">
          <i></i>${['Delivered', 'Cancelled', 'Returned'].includes(order.status) ? 'Closed' : 'Live tracking'}
        </span>
        <a class="btn btn-sm" href="/api/orders/${order.id}/invoice/" target="_blank" rel="noopener">GST invoice</a>
      </div>
    </div>`;

  const stepCount = order.total_amount ? 'Payment captured' : '';
  const detail = `
    <div class="grid-2">
      <section class="card pad">
        <div class="section-head"><h2 style="font-size:16px">Delivery progress</h2>
          <a class="link" href="/orders/">All orders →</a></div>
        ${timelineHtml(order)}
      </section>

      <div class="stack">
        <section class="card pad">
          <h2 style="font-size:16px;margin-bottom:12px">Items in this order</h2>
          <div class="order-items">
            ${order.items.map((item) => `
              <div class="order-line">
                <img src="${escapeHtml(item.image_url || '')}" alt="">
                <div class="grow">
                  <b>${escapeHtml(item.product_name)}</b>
                  <span>${escapeHtml(item.product_brand || '')} · Qty ${item.quantity}</span>
                  ${item.slug ? `<a class="link small" href="/p/${encodeURIComponent(item.slug)}/">Buy again</a>` : ''}
                </div>
                <div style="text-align:right">
                  <b>${money(item.line_total)}</b>
                  <span class="muted small" style="display:block">${money(item.unit_price)} each</span>
                </div>
              </div>`).join('')}
          </div>
          <hr class="divider">
          <div class="sum-row" style="padding:4px 0"><span>Subtotal</span><span>${money(order.subtotal)}</span></div>
          ${Number(order.discount_amount) > 0 ? `<div class="sum-row" style="padding:4px 0"><span>Coupon ${escapeHtml(order.coupon_code)}</span>
            <span class="free">− ${money(order.discount_amount)}</span></div>` : ''}
          <div class="sum-row" style="padding:4px 0"><span>Delivery</span>
            <span>${Number(order.delivery_fee) ? money(order.delivery_fee) : 'FREE'}</span></div>
          ${Number(order.cod_fee) > 0 ? `<div class="sum-row" style="padding:4px 0"><span>COD fee</span><span>${money(order.cod_fee)}</span></div>` : ''}
          <div class="sum-row total" style="padding-top:10px"><span>Total paid</span><span>${money(order.total_amount)}</span></div>
          <p class="tax-note" style="padding:4px 0">Includes ${money(order.gst_amount)} GST · invoice ${escapeHtml(order.invoice_number)}</p>
        </section>

        <section class="card pad">
          <div class="info-tiles">
            <div class="info-tile"><span class="label">Delivery address</span>
              <b>${escapeHtml(order.shipping_name)}</b>
              <span>${escapeHtml(order.full_address)}</span>
              <span>📞 ${escapeHtml(order.shipping_phone)}</span></div>
            <div class="info-tile"><span class="label">Payment</span>
              <b>${escapeHtml(order.payment_method_display)}</b>
              <span>${escapeHtml(order.payment_status)}${order.payment_reference ? ` · ${escapeHtml(order.payment_reference)}` : ''}</span>
              <span>${escapeHtml(stepCount)}</span></div>
          </div>
          <div class="pill-row" style="margin-top:14px">
            ${order.is_cancellable ? '<button class="btn btn-danger" type="button" id="cancel-btn">Cancel order</button>' : ''}
            ${order.is_returnable ? '<button class="btn btn-outline" type="button" id="return-btn">Return / replace</button>' : ''}
            <a class="btn" href="/shop/">Continue shopping</a>
          </div>
        </section>

        ${order.returns.length ? `<section class="card pad">
          <h2 style="font-size:15px;margin-bottom:10px">Return requests</h2>
          ${order.returns.map((row) => `
            <div class="order-line" style="margin-bottom:8px">
              <div class="grow"><b>${escapeHtml(row.reason_display)}</b>
                <span>${escapeHtml(row.comment || '')} · requested ${formatDate(row.created_at)}</span></div>
              <span class="badge ${row.status === 'Refunded' ? 'green' : row.status === 'Rejected' ? 'red' : 'amber'}">${escapeHtml(row.status)}</span>
            </div>`).join('')}
        </section>` : ''}
      </div>
    </div>`;

  root.innerHTML = hero + detail;
  bindActions();
}

/* ----------------------------------------------------------------- actions */

async function cancelOrder() {
  const okay = await confirmDialog({
    title: `Cancel ${order.order_number}?`,
    message: order.payment_status === 'Paid'
      ? 'Your payment will be refunded to the original method within 3–5 business days.'
      : 'The stock will be released back to the catalogue immediately.',
    confirmLabel: 'Cancel order',
    danger: true,
  });
  if (!okay) return;
  try {
    const data = await api.cancelOrder(order.id, 'Changed mind');
    toast(data.message, 'success');
    refresh({ silent: true });
  } catch (error) {
    toast(error.message, 'error');
  }
}

function requestReturn() {
  openModal({
    title: 'Request a return',
    body: `
      <p class="muted small" style="margin-bottom:14px">Refund goes to ${escapeHtml(order.payment_method_display)} after pickup.</p>
      <form id="return-form">
        <div class="field"><label>Reason</label>
          <select name="reason">${REASONS.map(([value, label]) => `<option value="${value}">${label}</option>`).join('')}</select></div>
        <div class="field"><label>Tell us more (optional)</label>
          <textarea name="comment" maxlength="1000" placeholder="What went wrong?"></textarea></div>
        <div class="form-actions"><button class="btn btn-primary" type="submit">Submit request</button></div>
      </form>`,
    onMount(el, close) {
      el.querySelector('#return-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        try {
          const data = await api.returnOrder(order.id, Object.fromEntries(new FormData(event.target).entries()));
          toast(data.message, 'success');
          close();
          refresh({ silent: true });
        } catch (error) {
          toast(error.message, 'error');
        }
      });
    },
  });
}

function bindActions() {
  const cancel = document.getElementById('cancel-btn');
  if (cancel) cancel.addEventListener('click', cancelOrder);
  const ret = document.getElementById('return-btn');
  if (ret) ret.addEventListener('click', requestReturn);
}

/* -------------------------------------------------------------- live stream */

function stopLive() {
  if (stream) { stream.close(); stream = null; }
  clearTimeout(pollTimer);
}

function startLive() {
  stopLive();
  if (['Delivered', 'Cancelled', 'Returned'].includes(order.status)) return;
  if (!window.EventSource) { pollTimer = setTimeout(() => refresh({ silent: true }), 15000); return; }

  stream = new EventSource(`/api/orders/${order.id}/stream/`);
  stream.addEventListener('order', (event) => {
    const payload = JSON.parse(event.data);
    const changed = payload.status !== order.status;
    order.status = payload.status;
    order.status_display = payload.status;
    order.payment_status = payload.payment_status;
    order.delivered_at = payload.delivered_at;
    order.events = payload.events;
    render();
    if (changed) {
      toast(`Order update: ${payload.status}`, 'info');
      if (['Delivered', 'Cancelled', 'Returned'].includes(payload.status)) stopLive();
    }
  });
  stream.onerror = () => {
    stopLive();
    pollTimer = setTimeout(() => refresh({ silent: true }), 12000);
  };
}

async function refresh({ silent = false } = {}) {
  try {
    const data = await api.order(orderId);
    const statusChanged = order && order.status !== data.status;
    order = data;
    render();
    if (statusChanged) toast(`Order update: ${data.status}`, 'info');
    startLive();
  } catch (error) {
    if (silent) return;
    root.innerHTML = `<div class="card empty"><span class="ico">🔎</span><h2>Order not found</h2>
      <p>${escapeHtml(error.message)}</p><a class="btn btn-primary" href="/orders/">Back to my orders</a></div>`;
  }
}

(async () => {
  await refresh();
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && order) refresh({ silent: true });
  });
})();
