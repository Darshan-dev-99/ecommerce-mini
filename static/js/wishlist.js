/** Wishlist page: saved products with a one-click move to cart. */

import {
  api, productCard, escapeHtml, toast, refreshCartCount, wishlistState,
} from './api.js';

const grid = document.getElementById('wish-grid');
const subtitle = document.getElementById('wish-sub');

function card(product) {
  return `
    <div class="stack" style="gap:0">
      ${productCard(product)}
      <button class="btn ${product.in_stock ? 'btn-cart' : ''} btn-sm btn-block"
        type="button" data-move="${product.id}" ${product.in_stock ? '' : 'disabled'}>
        ${product.in_stock ? 'Move to cart' : 'Out of stock'}
      </button>
    </div>`;
}

async function load() {
  try {
    const data = await api.wishlist();
    wishlistState.ids = new Set(data.ids.map(Number));
    wishlistState.count = data.count;
    subtitle.textContent = `${data.count} saved item${data.count === 1 ? '' : 's'} · prices include GST`;
    grid.innerHTML = data.results.length
      ? data.results.map(card).join('')
      : `<div class="card empty" style="grid-column:1/-1"><span class="ico">♥</span>
           <h2>Your wishlist is empty</h2>
           <p>Tap the heart on any product to save it here for later.</p>
           <a class="btn btn-cart" href="/shop/">Find something you love</a></div>`;
  } catch (error) {
    grid.innerHTML = `<div class="card empty" style="grid-column:1/-1"><h2>Could not load your wishlist</h2>
      <p>${escapeHtml(error.message)}</p></div>`;
  }
}

grid.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-move]');
  if (!button) return;
  button.disabled = true;
  try {
    const result = await api.addToCart(Number(button.dataset.move), 1);
    toast(result.message, 'success');
    await refreshCartCount();
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    button.disabled = false;
  }
});

document.addEventListener('wishlist:change', () => load());

load();
