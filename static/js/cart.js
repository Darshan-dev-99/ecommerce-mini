/** Cart page: every mutation round-trips through the API and re-renders. */

import {
  api, money, plain, escapeHtml, toast, setCartCount, confirmDialog, thumb,
} from './api.js';

const itemsHost = document.getElementById('cart-items');
const savedSection = document.getElementById('saved-section');
const savedHost = document.getElementById('saved-items');
const summaryHost = document.getElementById('summary');
const offerHost = document.getElementById('offer-list');
const subtitle = document.getElementById('cart-sub');

let cart = null;

const count = (data) => data.items.reduce((total, item) => total + item.quantity, 0);
const saving = (data) => data.items.reduce(
  (total, item) => total + (Number(item.unit_mrp) - Number(item.unit_price)) * item.quantity, 0,
);

function itemHtml(item, saved) {
  const off = Number(item.unit_mrp) > Number(item.unit_price)
    ? Math.round((1 - Number(item.unit_price) / Number(item.unit_mrp)) * 100) : 0;
  const low = item.stock > 0 && item.stock <= 5;
  return `
    <div class="cart-item" data-item="${item.id}">
      ${thumb(item.image_url, item.product_name)}
      <div>
        <h3><a href="/p/${encodeURIComponent(item.slug)}/">${escapeHtml(item.product_name)}</a></h3>
        <div class="meta">BazaarNoon Assured · ${item.is_active ? (item.stock > 0 ? 'In stock' : 'Out of stock') : 'Unavailable'}</div>
        <div class="price-line">
          <b>${money(item.unit_price)}</b>
          ${off ? `<span class="muted" style="text-decoration:line-through">${money(item.unit_mrp)}</span>
                   <span style="color:var(--green);font-weight:700">${off}% off</span>` : ''}
        </div>
        ${low ? `<span class="oos">Only ${item.stock} left in stock</span>` : ''}
        <div class="cart-actions">
          ${saved
            ? `<button type="button" data-move>Move to cart</button>`
            : `<button type="button" data-save>Save for later</button>`}
          <button type="button" data-remove>Remove</button>
        </div>
      </div>
      <div class="col-qty" style="display:grid;gap:8px;align-content:start;justify-items:end">
        ${saved
          ? `<span class="badge">Saved</span>`
          : `<div class="stepper">
               <button type="button" data-step="-1" ${item.quantity <= 1 ? 'disabled' : ''}>−</button>
               <span>${item.quantity}</span>
               <button type="button" data-step="1" ${item.quantity >= item.stock ? 'disabled' : ''}>+</button>
             </div>`}
        <b>${money(item.subtotal)}</b>
      </div>
    </div>`;
}

function summaryHtml(data) {
  const s = data.summary;
  const totalItems = count(data);
  const saved = saving(data);
  const gap = Number(s.free_delivery_gap);
  const coupon = data.coupon;

  return `
    ${saved > 0 ? `<div class="saving-banner">You save ${money(saved)} on this order 🎉</div>` : ''}
    ${gap > 0 ? `<div class="free-ship">🚚 Add ${money(gap)} more for free delivery</div>` : ''}
    <h3>Price details</h3>
    <div class="sum-row"><span>Price (${totalItems} item${totalItems === 1 ? '' : 's'})</span><span>${money(s.subtotal)}</span></div>
    ${Number(s.discount_amount) > 0
      ? `<div class="sum-row"><span>Coupon discount ${coupon ? `<span class="badge green">${escapeHtml(coupon.code)}</span>` : ''}</span>
           <span class="free">− ${money(s.discount_amount)}</span></div>` : ''}
    <div class="sum-row"><span>Delivery charges</span>
      ${Number(s.delivery_fee) === 0 ? '<span class="free">FREE</span>' : `<span>${money(s.delivery_fee)}</span>`}</div>
    ${Number(s.cod_fee) > 0 ? `<div class="sum-row"><span>COD handling fee</span><span>${money(s.cod_fee)}</span></div>` : ''}
    <div class="sum-row total"><span>Total amount</span><span>${money(s.total_amount)}</span></div>
    <p class="tax-note" style="padding:0 18px 8px">Inclusive of ${money(s.gst_amount)} GST</p>

    <div class="coupon-box">
      ${coupon
        ? `<div class="coupon-applied">
             <span><b>${escapeHtml(coupon.code)}</b> applied<br><span class="small">${escapeHtml(coupon.description || '')}</span></span>
             <button class="link-btn danger" type="button" data-remove-coupon>Remove</button>
           </div>`
        : `<form class="coupon-form" id="coupon-form">
             <input id="coupon-input" placeholder="Enter coupon code" aria-label="Coupon code" autocomplete="off">
             <button class="btn btn-sm" type="submit">Apply</button>
           </form>`}
    </div>

    <div class="summary-cta">
      <a class="btn btn-buy btn-block btn-lg ${data.stock_ok ? '' : 'disabled'}"
         href="${data.stock_ok ? '/checkout/' : '/cart/'}" ${data.stock_ok ? '' : 'aria-disabled="true"'}>Place order</a>
      <span class="muted small center">100% secure payments · UPI, cards, net banking, EMI</span>
    </div>`;
}

function render() {
  if (!cart) return;
  setCartCount(cart.item_count);

  if (!cart.items.length) {
    itemsHost.innerHTML = `
      <div class="empty">
        <span class="ico">🛒</span>
        <h2>Your cart is empty</h2>
        <p>Great deals are waiting — add something from the catalogue to get started.</p>
        <a class="btn btn-cart" href="/shop/">Start shopping</a>
      </div>`;
  } else {
    itemsHost.innerHTML = `
      <div class="pad-sm" style="border-bottom:1px solid var(--line-soft);display:flex;justify-content:space-between;align-items:center">
        <b>Cart (${cart.items.length} item${cart.items.length === 1 ? '' : 's'})</b>
        <span class="muted small">Deliver by ${new Date(Date.now() + Math.max(...cart.items.map((i) => i.product_detail.delivery_days)) * 86400000)
          .toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}</span>
      </div>
      ${cart.items.map((item) => itemHtml(item, false)).join('')}
      ${cart.issues.length ? `<div class="pad-sm" style="background:var(--red-soft);color:var(--red);font-size:13px">
        ${cart.issues.map((issue) => `<div>⚠ ${escapeHtml(issue.message)}</div>`).join('')}
      </div>` : ''}`;
  }

  savedSection.hidden = !cart.saved_items.length;
  savedHost.innerHTML = cart.saved_items.map((item) => itemHtml(item, true)).join('');
  summaryHost.innerHTML = cart.items.length ? summaryHtml(cart) : `
    <div class="empty"><span class="ico">🧾</span><h2>No price details yet</h2>
    <p>Add products to see the full break-up with GST and delivery.</p></div>`;
  subtitle.textContent = cart.items.length
    ? `${count(cart)} item${count(cart) === 1 ? '' : 's'} · prices include GST · free delivery above ₹${plain(cart.free_delivery_threshold)}`
    : 'Your cart is waiting.';
}

async function run(action, success) {
  try {
    const data = await action();
    if (data && data.cart) cart = data.cart;
    render();
    if (success) toast(typeof success === 'function' ? success(data) : success, 'success');
    if (data && data.cart) loadOffers();
  } catch (error) {
    toast(error.message, 'error');
  }
}

async function loadOffers() {
  try {
    const data = await api.cartOffers();
    offerHost.innerHTML = data.results.length ? data.results.map((coupon) => `
      <div class="coupon-applied" style="background:#f7faff;color:var(--ink);border:1px dashed #c5d7f8">
        <span><b>${escapeHtml(coupon.code)}</b> · ${escapeHtml(coupon.description || '')}
          <br><span class="small muted">${coupon.eligible
            ? `Save ${money(coupon.preview)} on this order`
            : `Add ${money(coupon.shortfall)} more to unlock`}</span></span>
        <button class="btn btn-sm ${coupon.eligible ? 'btn-outline' : ''}" type="button"
          data-apply="${escapeHtml(coupon.code)}" ${coupon.eligible ? '' : 'disabled'}>Apply</button>
      </div>`).join('') : '<p class="muted small">No coupons live right now.</p>';
  } catch {
    offerHost.innerHTML = '';
  }
}

/* --------------------------------------------------------------- listeners */

document.addEventListener('click', async (event) => {
  const itemEl = event.target.closest('[data-item]');
  if (!itemEl) return;
  const id = Number(itemEl.dataset.item);
  const line = cart.items.find((item) => item.id === id) || cart.saved_items.find((item) => item.id === id);
  if (!line) return;

  const step = event.target.closest('[data-step]');
  if (step) {
    const next = line.quantity + Number(step.dataset.step);
    if (next < 1) return;
    return run(() => api.updateCartItem(id, { quantity: next }));
  }
  if (event.target.closest('[data-remove]')) {
    const okay = await confirmDialog({
      title: 'Remove item?',
      message: `Remove ${line.product_name} from your cart?`,
      confirmLabel: 'Remove',
      danger: true,
    });
    if (!okay) return;
    return run(() => api.removeCartItem(id), 'Item removed from cart.');
  }
  if (event.target.closest('[data-save]')) {
    return run(() => api.updateCartItem(id, { saved_for_later: true }), 'Moved to saved for later.');
  }
  if (event.target.closest('[data-move]')) {
    return run(() => api.updateCartItem(id, { saved_for_later: false }), 'Moved back to your cart.');
  }
});

summaryHost.addEventListener('submit', (event) => {
  if (!event.target.matches('#coupon-form')) return;
  event.preventDefault();
  const code = document.getElementById('coupon-input').value.trim();
  if (!code) { toast('Enter a coupon code', 'error'); return; }
  run(() => api.applyCoupon(code), (data) => data.message);
});

summaryHost.addEventListener('click', (event) => {
  if (event.target.closest('[data-remove-coupon]')) {
    run(() => api.removeCoupon(), 'Coupon removed.');
  }
});

offerHost.addEventListener('click', (event) => {
  const button = event.target.closest('[data-apply]');
  if (!button) return;
  run(() => api.applyCoupon(button.dataset.apply), (data) => data.message);
});

/* ------------------------------------------------------------------- boot */

(async () => {
  try {
    cart = await api.cart();
    render();
    loadOffers();
  } catch (error) {
    itemsHost.innerHTML = `<div class="empty"><span class="ico">⚠️</span><h2>Could not load your cart</h2>
      <p>${escapeHtml(error.message)}</p></div>`;
  }
})();
