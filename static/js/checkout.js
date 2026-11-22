/** Checkout: saved addresses, payment choice, live re-quote, atomic placement. */

import {
  api, money, escapeHtml, toast, openModal, confirmDialog, setCartCount,
} from './api.js';

const addressHost = document.getElementById('address-step');
const paymentHost = document.getElementById('payment-step');
const itemsHost = document.getElementById('items-step');
const summaryHost = document.getElementById('checkout-summary');

const PAYMENTS = [
  { id: 'UPI', label: 'UPI', detail: 'Google Pay, PhonePe, Paytm · instant', ico: '📲', extra: 'Recommended' },
  { id: 'CARD', label: 'Credit / Debit card', detail: 'Visa, Mastercard, RuPay · 10% HDFC offer', ico: '💳' },
  { id: 'NETBANKING', label: 'Net banking', detail: 'All major Indian banks', ico: '🏦' },
  { id: 'EMI', label: 'EMI', detail: 'No cost EMI from ₹499/month', ico: '🗓️' },
  { id: 'COD', label: 'Cash on Delivery', detail: 'Pay in cash or UPI at your door', ico: '💵', fee: 49 },
];

const state = { cart: null, addresses: [], addressId: null, payment: 'UPI', quote: null, placing: false };

/* --------------------------------------------------------------- rendering */

function addressHtml() {
  if (!state.addresses.length) {
    return `<div class="empty" style="padding:26px 10px"><span class="ico">📍</span>
      <h2 style="font-size:17px">No saved address</h2>
      <p>Add a delivery address to continue — we deliver to 19,000+ pincodes.</p>
      <button class="btn btn-primary" type="button" data-add-address>Add address</button></div>`;
  }
  return `
    ${state.addresses.map((address) => `
      <label class="radio-card ${state.addressId === address.id ? 'is-on' : ''}" data-address="${address.id}">
        <input type="radio" name="address" ${state.addressId === address.id ? 'checked' : ''}>
        <div class="body">
          <b>${escapeHtml(address.full_name)} <span class="badge">${escapeHtml(address.label)}</span>
            ${address.is_default ? '<span class="tag">Default</span>' : ''}</b>
          <span>${escapeHtml(address.line1)}${address.line2 ? `, ${escapeHtml(address.line2)}` : ''},
            ${escapeHtml(address.city)}, ${escapeHtml(address.state)} — ${address.pincode}</span>
          <span>📞 ${escapeHtml(address.phone)}</span>
        </div>
        <button class="link-btn" type="button" data-edit-address="${address.id}">Edit</button>
      </label>`).join('')}
    <div class="row between" style="margin-top:6px">
      <button class="btn btn-outline btn-sm" type="button" data-add-address>+ Add new address</button>
      ${state.addresses.length > 1 ? '<button class="btn btn-ghost btn-sm" type="button" data-manage-addresses>Manage all</button>' : ''}
    </div>`;
}

function paymentHtml() {
  const codBlocked = Number(state.cart.summary.total_amount) > 50000;
  return PAYMENTS.map((option) => `
    <label class="pay-option ${state.payment === option.id ? 'is-on' : ''} ${option.id === 'COD' && codBlocked ? 'hidden' : ''}"
      data-pay="${option.id}">
      <input type="radio" name="payment" ${state.payment === option.id ? 'checked' : ''}>
      <span class="ico">${option.ico}</span>
      <span class="grow"><b>${option.label}</b><span>${option.detail}</span></span>
      <span class="extra">${option.id === state.payment && option.fee ? `+ ${money(option.fee)}` : (option.extra || '')}</span>
    </label>`).join('');
}

function itemsHtml() {
  return state.cart.items.map((item) => `
    <div class="order-line">
      <img src="${escapeHtml(item.image_url || '')}" alt="">
      <div class="grow">
        <b>${escapeHtml(item.product_name)}</b>
        <span>Qty ${item.quantity} · ${money(item.unit_price)} each</span>
      </div>
      <b>${money(item.subtotal)}</b>
    </div>`).join('');
}

function summaryHtml() {
  const q = state.quote || state.cart.summary;
  const address = state.addresses.find((row) => row.id === state.addressId);
  return `
    <div class="saving-banner">Delivering to ${address ? `${escapeHtml(address.city)} — ${address.pincode}` : 'select an address'}</div>
    <h3>Price details</h3>
    <div class="sum-row"><span>Price (${state.cart.items.reduce((n, i) => n + i.quantity, 0)} items)</span><span>${money(q.subtotal)}</span></div>
    ${Number(q.discount_amount) > 0 ? `<div class="sum-row"><span>Coupon discount</span>
      <span class="free">− ${money(q.discount_amount)}</span></div>` : ''}
    <div class="sum-row"><span>Delivery</span>
      ${Number(q.delivery_fee) === 0 ? '<span class="free">FREE</span>' : `<span>${money(q.delivery_fee)}</span>`}</div>
    ${Number(q.cod_fee) > 0 ? `<div class="sum-row"><span>COD handling</span><span>${money(q.cod_fee)}</span></div>` : ''}
    <div class="sum-row total"><span>Total payable</span><span>${money(q.total_amount)}</span></div>
    <p class="tax-note" style="padding:0 18px 6px">Includes ${money(q.gst_amount)} GST</p>
    ${q.delivery ? `<div class="free-ship">🚚 ${escapeHtml(q.delivery.city)} · arrives in ${q.delivery.eta_min_days}–${q.delivery.eta_max_days} days</div>` : ''}
    <div class="summary-cta">
      <button class="btn btn-buy btn-block btn-lg" type="button" id="place-order"
        ${state.addressId && !state.placing ? '' : 'disabled'}>
        ${state.placing ? '<span class="spinner"></span> Placing order…' : 'Place order'}
      </button>
      <span class="muted small center">By placing this order you agree to our terms &amp; return policy.</span>
    </div>`;
}

function paint() {
  addressHost.innerHTML = addressHtml();
  paymentHost.innerHTML = paymentHtml();
  itemsHost.innerHTML = itemsHtml();
  summaryHost.innerHTML = summaryHtml();
  document.getElementById('address-done').textContent = state.addressId ? '✓ Selected' : '';
  document.getElementById('items-done').textContent = `${state.cart.items.length} item${state.cart.items.length === 1 ? '' : 's'}`;
  document.getElementById('checkout-sub').textContent = `Order total ${money((state.quote || state.cart.summary).total_amount)} — prices include GST.`;
}

/* ------------------------------------------------------------------ quote */

async function requote() {
  const address = state.addresses.find((row) => row.id === state.addressId);
  try {
    state.quote = await api.quote({
      payment_method: state.payment,
      pincode: address ? address.pincode : '',
      coupon_code: state.cart.coupon ? state.cart.coupon.code : '',
    });
  } catch (error) {
    toast(error.message, 'error');
  }
  paint();
}

/* --------------------------------------------------------------- addresses */

function addressForm(address = null) {
  return `
    <form id="address-form">
      <div class="form-grid">
        <div class="field"><label>Label</label>
          <select name="label">
            ${['Home', 'Work', 'Other'].map((label) => `<option ${address && address.label === label ? 'selected' : ''}>${label}</option>`).join('')}
          </select></div>
        <div class="field"><label>Full name</label>
          <input name="full_name" required value="${address ? escapeHtml(address.full_name) : ''}" placeholder="Recipient's name"></div>
        <div class="field"><label>Mobile number</label>
          <input name="phone" required inputmode="numeric" maxlength="10" value="${address ? address.phone : ''}" placeholder="10 digit mobile"></div>
        <div class="field span-2"><label>House / street</label>
          <input name="line1" required value="${address ? escapeHtml(address.line1) : ''}" placeholder="Flat 402, Sunrise Apartments"></div>
        <div class="field span-2"><label>Area / landmark</label>
          <input name="line2" value="${address ? escapeHtml(address.line2) : ''}" placeholder="Near Metro station"></div>
        <div class="field"><label>City</label>
          <input name="city" required value="${address ? escapeHtml(address.city) : ''}" placeholder="Bengaluru"></div>
        <div class="field"><label>State</label>
          <input name="state" required value="${address ? escapeHtml(address.state) : ''}" placeholder="Karnataka"></div>
        <div class="field"><label>Pincode</label>
          <input name="pincode" required inputmode="numeric" maxlength="6" value="${address ? address.pincode : ''}" placeholder="560001"></div>
        <div class="field"><label>&nbsp;</label>
          <label class="check"><input type="checkbox" name="is_default" ${address && address.is_default ? 'checked' : ''}> Make this my default</label></div>
      </div>
      <div class="form-actions"><button class="btn btn-primary" type="submit">Save address</button></div>
    </form>`;
}

function openAddressModal(address = null) {
  openModal({
    title: address ? 'Edit address' : 'Add delivery address',
    body: addressForm(address),
    onMount(el, close) {
      el.querySelector('#address-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const form = new FormData(event.target);
        const body = Object.fromEntries(form.entries());
        body.is_default = form.has('is_default');
        try {
          const saved = address
            ? await api.updateAddress(address.id, body)
            : await api.createAddress(body);
          toast('Address saved.', 'success');
          state.addresses = await api.addresses();
          state.addressId = saved.id;
          close();
          await requote();
        } catch (error) {
          toast(error.message, 'error');
        }
      });
    },
  });
}

/* ---------------------------------------------------------------- placement */

async function placeOrder() {
  if (state.placing) return;
  if (!state.addressId) { toast('Choose a delivery address first.', 'error'); return; }
  const address = state.addresses.find((row) => row.id === state.addressId);
  const okay = await confirmDialog({
    title: 'Place this order?',
    message: `${money((state.quote || state.cart.summary).total_amount)} payable via ${PAYMENTS.find((p) => p.id === state.payment).label}, delivering to ${address.city} ${address.pincode}.`,
    confirmLabel: 'Place order',
  });
  if (!okay) return;

  state.placing = true;
  summaryHost.innerHTML = summaryHtml();
  try {
    const data = await api.placeOrder({
      address_id: state.addressId,
      payment_method: state.payment,
      coupon_code: state.cart.coupon ? state.cart.coupon.code : '',
    });
    setCartCount(0);
    const order = data.order;
    openModal({
      title: 'Order placed 🎉',
      body: `
        <div class="stack">
          <p><b>${escapeHtml(order.order_number)}</b> is confirmed.</p>
          <div class="info-tiles">
            <div class="info-tile"><span class="label">Total paid</span><b>${money(order.total_amount)}</b>
              <span>${escapeHtml(order.payment_method_display)} · ${escapeHtml(order.payment_status)}</span></div>
            <div class="info-tile"><span class="label">Arriving by</span>
              <b>${new Date(order.delivery_eta).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}</b>
              <span>${escapeHtml(order.shipping_city)} ${order.shipping_pincode}</span></div>
          </div>
          <p class="muted small">Track live status, download the GST invoice and request returns from your order page.</p>
        </div>`,
      footer: `<a class="btn" href="/orders/">All orders</a>
        <a class="btn btn-primary" href="/orders/${order.id}/">Track this order</a>`,
      onMount(el) {
        setTimeout(() => { window.location.href = `/orders/${order.id}/`; }, 2600);
      },
    });
  } catch (error) {
    state.placing = false;
    paint();
    toast(error.message, 'error');
  }
}

/* --------------------------------------------------------------- listeners */

addressHost.addEventListener('click', async (event) => {
  const radioCard = event.target.closest('[data-address]');
  if (radioCard && !event.target.closest('[data-edit-address]')) {
    state.addressId = Number(radioCard.dataset.address);
    await requote();
    return;
  }
  if (event.target.closest('[data-add-address]')) { openAddressModal(); return; }
  const edit = event.target.closest('[data-edit-address]');
  if (edit) {
    event.preventDefault();
    const row = state.addresses.find((address) => address.id === Number(edit.dataset.editAddress));
    if (row) openAddressModal(row);
    return;
  }
  if (event.target.closest('[data-manage-addresses]')) { window.location.href = '/account/#addresses'; }
});

paymentHost.addEventListener('click', (event) => {
  const option = event.target.closest('[data-pay]');
  if (!option) return;
  state.payment = option.dataset.pay;
  requote();
});

summaryHost.addEventListener('click', (event) => {
  if (event.target.closest('#place-order')) placeOrder();
});

/* ------------------------------------------------------------------- boot */

(async () => {
  try {
    const [cart, addresses] = await Promise.all([api.cart(), api.addresses()]);
    state.cart = cart;
    state.addresses = addresses;
    if (!cart.items.length) {
      window.location.href = '/cart/';
      return;
    }
    const preferred = addresses.find((row) => row.is_default) || addresses[0];
    state.addressId = preferred ? preferred.id : null;
    if (cart.payment_method && cart.payment_method !== 'COD') state.payment = cart.payment_method;
    await requote();
  } catch (error) {
    toast(error.message, 'error');
    addressHost.innerHTML = `<div class="empty"><h2>Checkout unavailable</h2><p>${escapeHtml(error.message)}</p>
      <a class="btn btn-primary" href="/cart/">Back to cart</a></div>`;
  }
})();
