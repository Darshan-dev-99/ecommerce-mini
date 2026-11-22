/** Offers page: live coupons straight from the API plus category shortcuts. */

import { api, money, escapeHtml, toast } from './api.js';

const cards = document.getElementById('coupon-cards');
const categoriesHost = document.getElementById('offer-categories');

function couponCard(coupon) {
  const value = Number(coupon.value);
  const headline = coupon.discount_type === 'percent'
    ? `Extra ${value}% off`
    : `Flat ₹${value.toLocaleString('en-IN')} off`;
  const cap = Number(coupon.max_discount) > 0 ? ` · up to ${money(coupon.max_discount)}` : '';
  return `
    <article class="offer-card">
      <h3>${headline}</h3>
      <p>${escapeHtml(coupon.description || '')}</p>
      <p class="small">On orders above ${money(coupon.min_order_value)}${cap}</p>
      <button class="offer-code" type="button" data-copy="${escapeHtml(coupon.code)}">${escapeHtml(coupon.code)} · tap to copy</button>
    </article>`;
}

async function load() {
  try {
    const [offers, categories] = await Promise.all([api.offers(), api.categories()]);
    cards.innerHTML = offers.results.length
      ? offers.results.map(couponCard).join('')
      : '<p class="muted">No coupons are live right now — check back during the next sale.</p>';

    categoriesHost.innerHTML = categories.slice(0, 10).map((row) => `
      <a class="cat-circle" href="/shop/?category=${encodeURIComponent(row.slug)}">
        <span class="ico" aria-hidden="true">${escapeHtml(row.icon || '🛍️')}</span>
        <span>${escapeHtml(row.name)}</span>
      </a>`).join('');
  } catch (error) {
    cards.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

cards.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-copy]');
  if (!button) return;
  const code = button.dataset.copy;
  try {
    await navigator.clipboard.writeText(code);
    toast(`Coupon ${code} copied — paste it in your cart.`, 'success');
  } catch {
    toast(`Coupon code: ${code}`, 'info');
  }
});

load();
