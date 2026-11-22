/**
 * BazaarNoon storefront core.
 *
 * One module owns: the fetch client, session + wishlist state, the header
 * (search suggestions, category rail, account menu, cart badge) and the
 * shared rendering helpers every page uses.
 */

const CSRF_COOKIE = 'csrftoken';

/* ------------------------------------------------------------------ http */

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

function readCookie(name) {
  const match = document.cookie.match(new RegExp(`(^|;\\s*)${name}=([^;]*)`));
  return match ? decodeURIComponent(match[2]) : '';
}

function firstError(data) {
  if (!data) return '';
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) return data.length ? String(data[0]) : '';
  if (typeof data === 'object') {
    for (const [key, value] of Object.entries(data)) {
      if (key === 'detail' || key === 'message' || key === 'items') continue;
      const nested = firstError(value);
      if (nested) return nested;
    }
  }
  return '';
}

export async function request(path, { method = 'GET', body, signal } = {}) {
  const headers = { Accept: 'application/json' };
  const options = { method, headers, credentials: 'same-origin', signal };

  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    options.body = JSON.stringify(body);
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    headers['X-CSRFToken'] = readCookie(CSRF_COOKIE);
  }

  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new ApiError('Cannot reach the server. Check your connection.', 0, null);
  }

  if (response.status === 204) return null;

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { message: text.slice(0, 300) };
    }
  }

  if (!response.ok) {
    const message =
      (data && (data.message || (typeof data.detail === 'string' ? data.detail : ''))) ||
      firstError(data) ||
      `Request failed (${response.status})`;
    throw new ApiError(message, response.status, data);
  }
  return data;
}

/* -------------------------------------------------------------- formatting */

const inrFormat = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
  minimumFractionDigits: 0,
});

export const money = (value) => inrFormat.format(Number(value || 0));
export const plain = (value) =>
  Number(value || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 });

export const escapeHtml = (value) =>
  String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[char]);

export const initials = (name) =>
  String(name || '?')
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join('')
    .toUpperCase();

export const formatDate = (iso) => {
  if (!iso) return '';
  const date = new Date(iso);
  return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
};

export const formatDateTime = (iso) => {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-IN', {
    day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
};

export const timeAgo = (iso) => {
  if (!iso) return '';
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return 'just now';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
  const days = Math.floor(seconds / 86400);
  if (days < 30) return `${days} day${days > 1 ? 's' : ''} ago`;
  return formatDate(iso);
};

export const statusClass = (status) => String(status || '').replace(/\s+/g, '-');

export const daysUntil = (iso) => {
  if (!iso) return null;
  const target = new Date(iso);
  const today = new Date();
  target.setHours(0, 0, 0, 0);
  today.setHours(0, 0, 0, 0);
  return Math.round((target - today) / 86400000);
};

/* ------------------------------------------------------------- UI helpers */

export const stars = (rating) => {
  const value = Number(rating || 0);
  let html = '<span class="stars" aria-hidden="true">';
  for (let index = 1; index <= 5; index += 1) {
    html += `<span class="${value >= index - 0.25 ? '' : 'off'}">★</span>`;
  }
  return `${html}</span>`;
};

export const ratingPill = (product) => {
  const rating = Number(product.rating || 0);
  if (!rating) return '<span class="rating-pill empty">New</span>';
  return `<span class="rating-pill">${rating.toFixed(1)}<span class="star">★</span></span>`;
};

export function thumb(url, name, extraClass = '') {
  const label = escapeHtml(String(name || '?').charAt(0).toUpperCase());
  if (!url) {
    return `<div class="thumb ${extraClass}" aria-hidden="true"><div class="fallback">${label}</div></div>`;
  }
  return `<div class="thumb ${extraClass}"><img src="${escapeHtml(url)}" alt="" loading="lazy"
    onerror="this.style.display='none';this.parentElement.innerHTML='<div class=&quot;fallback&quot;>${label}</div>';"></div>`;
}

export function productCard(product, { compact = false } = {}) {
  const href = `/p/${encodeURIComponent(product.slug)}/`;
  const off = Number(product.discount_percent || 0);
  const badge = product.badge
    ? `<span class="p-badge ${/@|deal|offer/i.test(product.badge) ? 'orange' : ''}">${escapeHtml(product.badge)}</span>`
    : '';
  const stockLine = product.in_stock
    ? (Number(product.stock) <= 5 ? `<span class="oos" style="color:#b26a00">Only ${product.stock} left</span>` : '')
    : '<span class="oos">Out of stock</span>';
  const meta = compact ? '' : `
    <div class="p-meta">
      ${product.free_delivery ? '<span class="assured">Free delivery</span>' : `<span>Delivery in ${product.delivery_days} day${product.delivery_days > 1 ? 's' : ''}</span>`}
      ${product.cod_available ? '<span>COD</span>' : ''}
      ${product.sold_count ? `<span>${plain(product.sold_count)}+ bought</span>` : ''}
    </div>`;
  const wished = isWishlisted(product.id) ? 'is-on' : '';
  return `
    <article class="p-card" data-product="${product.id}">
      <a class="p-media" href="${href}" aria-label="${escapeHtml(product.name)}">
        ${product.image_url
          ? `<img src="${escapeHtml(product.image_url)}" alt="${escapeHtml(product.name)}" loading="lazy"
               onerror="this.remove();this.parentElement.insertAdjacentHTML('beforeend','<div class=&quot;fallback&quot;>${escapeHtml(String(product.name).charAt(0))}</div>')">`
          : `<div class="fallback">${escapeHtml(String(product.name).charAt(0))}</div>`}
        ${badge}
      </a>
      <button class="p-wish ${wished}" type="button" data-wish="${product.id}" aria-label="Save to wishlist" title="Save to wishlist">♥</button>
      <div class="p-body">
        <span class="p-brand">${escapeHtml(product.brand_name || product.category_name || '')}</span>
        <a class="p-name clamp-2" href="${href}">${escapeHtml(product.name)}</a>
        <div class="p-rating-row">${ratingPill(product)}<span class="count">(${plain(product.rating_count)})</span></div>
        <div class="p-price">
          <span class="now">${money(product.price)}</span>
          ${off > 0 ? `<span class="mrp">${money(product.mrp)}</span><span class="off">${off}% off</span>` : ''}
        </div>
        ${stockLine}
        ${meta}
      </div>
    </article>`;
}

export function skeletons(count = 8) {
  return Array.from({ length: count }, () => '<div class="skeleton sk-card"></div>').join('');
}

/* ------------------------------------------------------------------ toasts */

export function toast(message, type = 'info', timeout = 3600) {
  const host = document.getElementById('toasts');
  if (!host) return;
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = message;
  host.appendChild(el);
  const remove = () => {
    el.classList.add('is-leaving');
    setTimeout(() => el.remove(), 220);
  };
  setTimeout(remove, timeout);
  el.addEventListener('click', remove);
}

/* ------------------------------------------------------------------- modal */

export function openModal({ title, body, footer, onMount, wide = false }) {
  const root = document.getElementById('modal-root');
  root.innerHTML = `
    <div class="modal-backdrop" role="dialog" aria-modal="true" aria-label="${escapeHtml(title)}">
      <div class="modal" ${wide ? 'style="width:min(860px,100%)"' : ''}>
        <div class="modal-head">
          <h2>${escapeHtml(title)}</h2>
          <button class="modal-close" type="button" aria-label="Close">&times;</button>
        </div>
        <div class="modal-body">${body}</div>
        ${footer ? `<div class="modal-body modal-foot">${footer}</div>` : ''}
      </div>
    </div>`;

  const backdrop = root.firstElementChild;
  const close = () => {
    root.innerHTML = '';
    document.removeEventListener('keydown', onKey);
  };
  const onKey = (event) => {
    if (event.key === 'Escape') close();
  };
  document.addEventListener('keydown', onKey);
  backdrop.addEventListener('click', (event) => {
    if (event.target === backdrop) close();
  });
  backdrop.querySelector('.modal-close').addEventListener('click', close);
  if (onMount) onMount(backdrop, close);
  return close;
}

export function confirmDialog({ title, message, confirmLabel = 'Confirm', danger = false }) {
  return new Promise((resolve) => {
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      resolve(value);
    };
    const root = document.getElementById('modal-root');
    const observer = new MutationObserver(() => {
      if (!root.innerHTML) {
        observer.disconnect();
        finish(false);
      }
    });
    observer.observe(root, { childList: true });

    openModal({
      title,
      body: `<p class="muted">${escapeHtml(message)}</p>`,
      footer: `
        <button class="btn" type="button" data-cancel>Cancel</button>
        <button class="btn ${danger ? 'btn-danger' : 'btn-primary'}" type="button" data-confirm>${escapeHtml(confirmLabel)}</button>`,
      onMount(el, closeFn) {
        el.querySelector('[data-cancel]').addEventListener('click', () => {
          finish(false);
          closeFn();
        });
        el.querySelector('[data-confirm]').addEventListener('click', () => {
          finish(true);
          closeFn();
        });
      },
    });
  });
}

/* ----------------------------------------------------------------- session */

export const session = { user: null, authenticated: false };
export const isAdmin = () => Boolean(session.user && session.user.is_store_admin);

export async function refreshSession() {
  try {
    const data = await request('/api/auth/me/');
    session.authenticated = Boolean(data.authenticated);
    session.user = data.user || null;
  } catch {
    session.authenticated = false;
    session.user = null;
  }
  return session;
}

export const wishlistState = { ids: new Set(), count: 0 };
export const isWishlisted = (id) => wishlistState.ids.has(Number(id));

export async function refreshWishlist() {
  if (!session.authenticated) {
    wishlistState.ids = new Set();
    wishlistState.count = 0;
    return wishlistState;
  }
  try {
    const data = await request('/api/wishlist/');
    wishlistState.ids = new Set((data.ids || []).map(Number));
    wishlistState.count = data.count || 0;
    syncWishButtons();
  } catch { /* keep previous state */ }
  return wishlistState;
}

function syncWishButtons() {
  document.querySelectorAll('[data-wish]').forEach((button) => {
    button.classList.toggle('is-on', isWishlisted(button.dataset.wish));
  });
  const badge = document.getElementById('wish-count');
  if (badge) {
    badge.textContent = wishlistState.count;
    badge.hidden = wishlistState.count === 0;
  }
}

/* ------------------------------------------------------------------- shell */

function renderNav() {
  document.querySelectorAll('[data-auth-only]').forEach((el) => {
    el.classList.toggle('hidden', !session.authenticated);
  });
  document.querySelectorAll('[data-admin-only]').forEach((el) => {
    el.classList.toggle('hidden', !isAdmin());
  });
  document.querySelectorAll('[data-guest-only]').forEach((el) => {
    el.classList.toggle('hidden', session.authenticated);
  });

  const active = document.body.dataset.nav;
  document.querySelectorAll('[data-nav-link]').forEach((link) => {
    link.classList.toggle('is-on', link.dataset.navLink === active);
  });

  const area = document.getElementById('account-area');
  if (!area) return;

  if (!session.authenticated) {
    area.innerHTML = `
      <a class="btn btn-block btn-sm" style="background:#fff;color:#2874f0;border-color:#fff" href="/login/?next=${encodeURIComponent(location.pathname + location.search)}">Login</a>`;
    return;
  }

  const name = session.user.display_name || session.user.username;
  area.innerHTML = `
    <button class="user-chip" type="button" id="account-btn" aria-haspopup="menu" aria-expanded="false">
      <span class="avatar">${escapeHtml(initials(name))}</span>
      <span>${escapeHtml(name.split(' ')[0])}</span>
      <svg width="10" height="10" viewBox="0 0 10 10" aria-hidden="true"><path d="M1 3l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
    </button>
    <div class="menu hidden" id="account-menu" role="menu">
      <div class="menu-head">
        <b>${escapeHtml(name)}</b>
        <span>${escapeHtml(session.user.email || session.user.phone || 'Signed in')}</span>
      </div>
      <a href="/orders/">My orders</a>
      <a href="/wishlist/">My wishlist</a>
      <a href="/account/">Profile &amp; addresses</a>
      ${isAdmin() ? '<hr><a href="/manage/">Seller console</a><a href="/manage/products/">Manage products</a>' : ''}
      <hr>
      <button type="button" id="logout-btn">Log out</button>
    </div>`;

  const button = area.querySelector('#account-btn');
  const menu = area.querySelector('#account-menu');
  const closeMenu = () => {
    menu.classList.add('hidden');
    button.setAttribute('aria-expanded', 'false');
  };
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    const isHidden = menu.classList.toggle('hidden');
    button.setAttribute('aria-expanded', String(!isHidden));
  });
  document.addEventListener('click', (event) => {
    if (!menu.contains(event.target) && event.target !== button) closeMenu();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeMenu();
  });

  area.querySelector('#logout-btn').addEventListener('click', async () => {
    try {
      await request('/api/auth/logout/', { method: 'POST' });
      toast('Signed out. See you soon!', 'success');
      setTimeout(() => { window.location.href = '/'; }, 350);
    } catch (error) {
      toast(error.message, 'error');
    }
  });
}

export function setCartCount(count) {
  const badge = document.getElementById('cart-count');
  if (!badge) return;
  const value = Number(count) || 0;
  const changed = badge.textContent !== String(value);
  badge.textContent = value > 99 ? '99+' : String(value);
  badge.hidden = value === 0;
  if (changed) {
    badge.classList.remove('is-bumped');
    void badge.offsetWidth;
    badge.classList.add('is-bumped');
  }
}

export async function refreshCartCount() {
  if (!session.authenticated) {
    setCartCount(0);
    return;
  }
  try {
    const cart = await request('/api/cart/');
    setCartCount(cart.item_count);
  } catch { /* keep the previous badge */ }
}

export function requireAuth(next = window.location.pathname + window.location.search) {
  if (session.authenticated) return true;
  window.location.href = `/login/?next=${encodeURIComponent(next)}`;
  return false;
}

/* ------------------------------------------------------------------ header */

async function loadCategories() {
  const host = document.getElementById('catbar');
  if (!host) return;
  const params = new URLSearchParams(location.search);
  const current = params.get('category') || '';
  try {
    const rows = await request('/api/categories/');
    const all = `<a class="cat-chip ${current ? '' : 'is-active'}" href="/shop/">All</a>`;
    host.innerHTML = all + rows.map((row) => `
      <a class="cat-chip ${current === row.slug ? 'is-active' : ''}" href="/shop/?category=${encodeURIComponent(row.slug)}">
        <span aria-hidden="true">${escapeHtml(row.icon || '')}</span>${escapeHtml(row.name)}
      </a>`).join('');
  } catch { /* leave the default chip */ }
}

function initSearch() {
  const form = document.getElementById('search-form');
  const input = document.getElementById('search-input');
  const panel = document.getElementById('suggest');
  if (!form || !input || !panel) return;

  const params = new URLSearchParams(location.search);
  if (params.get('search')) input.value = params.get('search');

  let timer = null;
  let controller = null;
  let active = -1;
  let items = [];

  const reset = () => {
    panel.hidden = true;
    panel.innerHTML = '';
    items = [];
    active = -1;
  };

  const go = (url) => { window.location.href = url; };

  const render = (data) => {
    const q = data.query || input.value.trim();
    const blocks = [];
    if (data.categories.length) {
      blocks.push('<div class="suggest-group">Categories</div>');
      data.categories.forEach((row) => blocks.push(
        `<div class="suggest-item" data-href="/shop/?category=${encodeURIComponent(row.slug)}">🏷️ ${escapeHtml(row.name)}</div>`,
      ));
    }
    if (data.brands.length) {
      blocks.push('<div class="suggest-group">Brands</div>');
      data.brands.forEach((row) => blocks.push(
        `<div class="suggest-item" data-href="/shop/?brand=${encodeURIComponent(row.slug)}">✨ ${escapeHtml(row.name)}</div>`,
      ));
    }
    if (data.products.length) {
      blocks.push('<div class="suggest-group">Products</div>');
      data.products.forEach((row) => blocks.push(`
        <div class="suggest-item" data-href="/p/${encodeURIComponent(row.slug)}/">
          <img src="${escapeHtml(row.image_url)}" alt="" loading="lazy">
          <span class="grow truncate">${escapeHtml(row.name)}</span>
          <span class="s-price">${money(row.price)}</span>
        </div>`));
    }
    if (!blocks.length) {
      blocks.push(`<div class="suggest-item" data-href="/shop/?search=${encodeURIComponent(q)}">Search for “${escapeHtml(q)}”</div>`);
    } else {
      blocks.push(`<div class="suggest-item" data-href="/shop/?search=${encodeURIComponent(q)}">See all results for “${escapeHtml(q)}”</div>`);
    }
    panel.innerHTML = blocks.join('');
    panel.hidden = false;
    items = [...panel.querySelectorAll('.suggest-item')];
    active = -1;
  };

  const lookup = async () => {
    const query = input.value.trim();
    if (query.length < 2) { reset(); return; }
    if (controller) controller.abort();
    controller = new AbortController();
    try {
      const data = await request(`/api/search/suggest/?q=${encodeURIComponent(query)}`, { signal: controller.signal });
      render(data);
    } catch { /* aborted or offline */ }
  };

  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(lookup, 200);
  });
  input.addEventListener('focus', () => { if (items.length) panel.hidden = false; });
  input.addEventListener('keydown', (event) => {
    if (panel.hidden) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      active = (active + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items.forEach((item, index) => item.classList.toggle('is-active', index === active));
    } else if (event.key === 'Enter' && active >= 0) {
      event.preventDefault();
      go(items[active].dataset.href);
    } else if (event.key === 'Escape') {
      reset();
    }
  });
  panel.addEventListener('mousedown', (event) => {
    const item = event.target.closest('.suggest-item');
    if (item) { event.preventDefault(); go(item.dataset.href); }
  });
  document.addEventListener('click', (event) => {
    if (!form.contains(event.target)) reset();
  });

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const query = input.value.trim();
    window.location.href = query ? `/shop/?search=${encodeURIComponent(query)}` : '/shop/';
  });
}

function initWishlistDelegate() {
  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-wish]');
    if (!button) return;
    event.preventDefault();
    if (!session.authenticated) {
      requireAuth();
      return;
    }
    const productId = Number(button.dataset.wish);
    button.disabled = true;
    try {
      const result = await request('/api/wishlist/', { method: 'POST', body: { product: productId } });
      if (result.wishlisted) wishlistState.ids.add(productId);
      else wishlistState.ids.delete(productId);
      wishlistState.count = result.count;
      syncWishButtons();
      toast(result.message, result.wishlisted ? 'success' : 'info');
      document.dispatchEvent(new CustomEvent('wishlist:change', { detail: { productId, wishlisted: result.wishlisted } }));
    } catch (error) {
      toast(error.message, 'error');
    } finally {
      button.disabled = false;
    }
  });
}

/* --------------------------------------------------------------------- api */

const query = (params = {}) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') search.set(key, value);
  });
  const text = search.toString();
  return text ? `?${text}` : '';
};

export const api = {
  me: () => request('/api/auth/me/'),
  login: (body) => request('/api/auth/login/', { method: 'POST', body }),
  register: (body) => request('/api/auth/register/', { method: 'POST', body }),
  logout: () => request('/api/auth/logout/', { method: 'POST' }),
  updateProfile: (body) => request('/api/auth/me/', { method: 'PATCH', body }),

  home: () => request('/api/home/'),
  categories: () => request('/api/categories/'),
  brands: () => request('/api/brands/'),
  createCategory: (body) => request('/api/categories/', { method: 'POST', body }),
  updateCategory: (id, body) => request(`/api/categories/${id}/`, { method: 'PATCH', body }),
  deleteCategory: (id) => request(`/api/categories/${id}/`, { method: 'DELETE' }),

  products: (params = {}) => request(`/api/products/${query(params)}`),
  product: (slug) => request(`/api/products/${encodeURIComponent(slug)}/`),
  reviews: (slug) => request(`/api/products/${encodeURIComponent(slug)}/reviews/`),
  addReview: (slug, body) => request(`/api/products/${encodeURIComponent(slug)}/reviews/`, { method: 'POST', body }),
  createProduct: (body) => request('/api/products/', { method: 'POST', body }),
  updateProduct: (id, body) => request(`/api/products/${id}/`, { method: 'PATCH', body }),
  deleteProduct: (id) => request(`/api/products/${id}/`, { method: 'DELETE' }),

  offers: () => request('/api/offers/'),
  pincode: (code) => request(`/api/pincodes/${encodeURIComponent(code)}/`),
  recentlyViewed: () => request('/api/recently-viewed/'),

  cart: (params = {}) => request(`/api/cart/${query(params)}`),
  clearCart: () => request('/api/cart/', { method: 'DELETE' }),
  addToCart: (product, quantity = 1) => request('/api/cart/items/', { method: 'POST', body: { product, quantity } }),
  updateCartItem: (id, body) => request(`/api/cart/items/${id}/`, { method: 'PATCH', body }),
  removeCartItem: (id) => request(`/api/cart/items/${id}/`, { method: 'DELETE' }),
  applyCoupon: (code) => request('/api/cart/coupon/', { method: 'POST', body: { code } }),
  removeCoupon: () => request('/api/cart/coupon/', { method: 'DELETE' }),
  cartOffers: () => request('/api/cart/offers/'),
  quote: (body) => request('/api/cart/quote/', { method: 'POST', body }),

  orders: (params = {}) => request(`/api/orders/${query(params)}`),
  order: (id) => request(`/api/orders/${id}/`),
  placeOrder: (body) => request('/api/orders/', { method: 'POST', body }),
  cancelOrder: (id, reason = '') => request(`/api/orders/${id}/cancel/`, { method: 'POST', body: { reason } }),
  setOrderStatus: (id, body) => request(`/api/orders/${id}/status/`, { method: 'PATCH', body }),
  returnOrder: (id, body) => request(`/api/orders/${id}/return/`, { method: 'POST', body }),
  orderSummary: () => request('/api/orders/summary/'),

  addresses: () => request('/api/addresses/'),
  createAddress: (body) => request('/api/addresses/', { method: 'POST', body }),
  updateAddress: (id, body) => request(`/api/addresses/${id}/`, { method: 'PATCH', body }),
  deleteAddress: (id) => request(`/api/addresses/${id}/`, { method: 'DELETE' }),

  wishlist: () => request('/api/wishlist/'),
  toggleWishlist: (product) => request('/api/wishlist/', { method: 'POST', body: { product } }),

  dashboard: () => request('/api/admin/dashboard/'),
  adminOverview: () => request('/api/admin/overview/'),
  customers: () => request('/api/admin/customers/'),
  coupons: () => request('/api/admin/coupons/'),
  createCoupon: (body) => request('/api/admin/coupons/', { method: 'POST', body }),
  updateCoupon: (id, body) => request(`/api/admin/coupons/${id}/`, { method: 'PATCH', body }),
  deleteCoupon: (id) => request(`/api/admin/coupons/${id}/`, { method: 'DELETE' }),
  returns: (params = {}) => request(`/api/admin/returns/${query(params)}`),
  resolveReturn: (id, body) => request(`/api/admin/returns/${id}/resolve/`, { method: 'POST', body }),

  cacheStats: () => request('/api/system/cache-stats/'),
  simulate: (probe) => request('/api/system/simulate/', { method: 'POST', body: { probe } }),
  warmCache: () => request('/api/system/cache/warm/', { method: 'POST' }),
  resetCache: () => request('/api/system/cache/reset/', { method: 'POST' }),
  health: () => request('/api/system/health/'),
};

/* ------------------------------------------------------------------- boot */

export const sessionReady = (async () => {
  await refreshSession();
  renderNav();
  initSearch();
  initWishlistDelegate();
  await Promise.all([refreshCartCount(), refreshWishlist(), loadCategories()]);
})();

export const qs = {
  get: (key, fallback = '') => new URLSearchParams(location.search).get(key) ?? fallback,
  all: () => Object.fromEntries(new URLSearchParams(location.search).entries()),
  set: (values) => {
    const params = new URLSearchParams(location.search);
    Object.entries(values).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '' || value === 'all') params.delete(key);
      else params.set(key, value);
    });
    const text = params.toString();
    history.replaceState(null, '', text ? `${location.pathname}?${text}` : location.pathname);
  },
};
