/** Seller catalogue: filter, search, inline stock control and a full product editor. */

import {
  api, money, plain, escapeHtml, thumb, qs,
  toast, openModal, confirmDialog, sessionReady, session,
} from './api.js';

const $ = (id) => document.getElementById(id);
const PAGE_SIZE = 20;

const state = {
  search: qs.get('search') || '',
  category: qs.get('category') || '',
  ordering: qs.get('ordering') || 'newest',
  low: qs.get('stock') === 'low',
  inactive: true,
  page: Math.max(1, Number(qs.get('page') || 1)),
};

let brands = [];
let categories = [];
let payload = { results: [], count: 0, pages: 1 };

/* ------------------------------------------------------------------ helpers */

function fieldError(error) {
  const data = error.data;
  if (!data || typeof data !== 'object') return error.message;
  if (data.detail) return Array.isArray(data.detail) ? data.detail[0] : String(data.detail);
  const key = Object.keys(data)[0];
  if (!key) return error.message;
  const value = data[key];
  return `${key.replace(/_/g, ' ')}: ${Array.isArray(value) ? value[0] : value}`;
}

function syncUrl() {
  qs.set({
    search: state.search,
    category: state.category === '' ? '' : state.category,
    ordering: state.ordering === 'newest' ? '' : state.ordering,
    stock: state.low ? 'low' : '',
    page: state.page === 1 ? '' : state.page,
  });
}

/* ---------------------------------------------------------------- rendering */

function stockCell(product) {
  const stock = Number(product.stock);
  const tone = stock === 0 ? 'var(--red)' : stock <= 5 ? 'var(--amber)' : 'var(--ink)';
  return `
    <div class="row" style="gap:4px;justify-content:flex-end">
      <button class="btn btn-sm" type="button" data-stock-minus="${product.id}" aria-label="Decrease stock">−</button>
      <b style="min-width:34px;text-align:center;color:${tone}">${stock}</b>
      <button class="btn btn-sm" type="button" data-stock-plus="${product.id}" aria-label="Increase stock">+</button>
    </div>`;
}

function rowHtml(product) {
  const inactive = !product.is_active;
  return `
    <tr data-row="${product.id}" style="${inactive ? 'opacity:.6' : ''}">
      <td>
        <div class="table-prod">
          ${thumb(product.image_url, product.name)}
          <div style="min-width:0">
            <a class="link clamp-2" href="/p/${encodeURIComponent(product.slug)}/" target="_blank" rel="noopener">${escapeHtml(product.name)}</a>
            <div class="small muted">${escapeHtml(product.category_name || '—')} · ${escapeHtml(product.brand_name || 'No brand')}</div>
          </div>
        </div>
      </td>
      <td class="small">${escapeHtml(product.category_name || '—')}</td>
      <td class="num">${money(product.price)}${product.discount_percent ? `<div class="small" style="color:var(--green)">${product.discount_percent}% off</div>` : ''}</td>
      <td class="num small muted">${money(product.mrp)}</td>
      <td class="num">${stockCell(product)}</td>
      <td class="num small muted">${plain(product.sold_count)}</td>
      <td>
        <button class="status-chip ${product.in_stock ? 'status-Delivered' : 'status-Cancelled'}" type="button"
          data-toggle="${product.id}" title="Toggle availability">
          ${product.is_active ? (product.in_stock ? 'Live' : 'Out of stock') : 'Inactive'}
        </button>
      </td>
      <td>
        <div class="table-actions">
          <button class="link-btn" type="button" data-edit="${product.id}">Edit</button>
          <button class="link-btn danger" type="button" data-delete="${product.id}">Delete</button>
        </div>
      </td>
    </tr>`;
}

function render() {
  let rows = payload.results;
  if (state.low) rows = rows.filter((product) => Number(product.stock) <= 5);

  $('products-sub').textContent =
    `${payload.count} product${payload.count === 1 ? '' : 's'} in the catalogue${state.low ? ' · low stock filter on' : ''}`;

  const body = document.querySelector('#products-table tbody');
  body.innerHTML = rows.length
    ? rows.map(rowHtml).join('')
    : '<tr><td colspan="8" class="muted">No products match these filters.</td></tr>';

  const pages = payload.pages || 1;
  const buttons = [];
  for (let page = 1; page <= pages; page += 1) {
    if (pages > 9 && page !== 1 && page !== pages && Math.abs(page - state.page) > 1) {
      if (buttons[buttons.length - 1] !== '…') buttons.push('…');
      continue;
    }
    buttons.push(page);
  }
  $('product-pagination').innerHTML = pages > 1
    ? buttons.map((item) => (item === '…'
      ? '<span class="page-btn" aria-hidden="true">…</span>'
      : `<button class="page-btn${item === state.page ? ' is-on' : ''}" type="button" data-page="${item}">${item}</button>`)).join('')
    : '';
}

/* --------------------------------------------------------------------- load */

async function load() {
  const params = {
    page: state.page,
    page_size: PAGE_SIZE,
    ordering: state.ordering,
  };
  if (state.search) params.search = state.search;
  if (state.category) params.category = state.category;
  if (state.inactive) params.include_inactive = 'true';

  try {
    payload = await api.products(params);
    if (state.low) payload = { ...payload, results: payload.results.filter((row) => Number(row.stock) <= 5) };
    render();
    syncUrl();
  } catch (error) {
    toast(error.message, 'error');
    document.querySelector('#products-table tbody').innerHTML =
      `<tr><td colspan="8" class="muted">${escapeHtml(error.message)}</td></tr>`;
  }
}

/* -------------------------------------------------------------- stock / state */

async function patchProduct(id, body, message) {
  try {
    const updated = await api.updateProduct(id, body);
    const index = payload.results.findIndex((row) => row.id === id);
    if (index >= 0) payload.results[index] = { ...payload.results[index], ...updated };
    render();
    toast(message, 'success');
  } catch (error) {
    toast(fieldError(error), 'error');
  }
}

/* --------------------------------------------------------------- the editor */

function selectOptions(rows, selected, placeholder) {
  return `<option value="">${escapeHtml(placeholder)}</option>` + rows.map((row) => `
    <option value="${row.id}"${String(row.id) === String(selected) ? ' selected' : ''}>${escapeHtml(row.name)}</option>`).join('');
}

function formHtml(product = {}) {
  const value = (key, fallback = '') => escapeHtml(product[key] ?? fallback);
  return `
    <form id="product-form" novalidate>
      <div class="field">
        <label for="pf-name">Product name *</label>
        <input class="input" id="pf-name" value="${value('name')}" required maxlength="200">
      </div>
      <div class="form-grid">
        <div class="field">
          <label for="pf-category">Category *</label>
          <select class="select" id="pf-category" required>${selectOptions(categories, product.category, 'Choose a category')}</select>
        </div>
        <div class="field">
          <label for="pf-brand">Brand</label>
          <select class="select" id="pf-brand">${selectOptions(brands, product.brand, 'No brand')}</select>
        </div>
        <div class="field">
          <label for="pf-price">Selling price (₹) *</label>
          <input class="input" id="pf-price" type="number" min="1" step="1" value="${value('price')}" required>
        </div>
        <div class="field">
          <label for="pf-mrp">MRP (₹)</label>
          <input class="input" id="pf-mrp" type="number" min="0" step="1" value="${value('mrp')}">
        </div>
        <div class="field">
          <label for="pf-stock">Stock *</label>
          <input class="input" id="pf-stock" type="number" min="0" step="1" value="${value('stock', 0)}" required>
        </div>
        <div class="field">
          <label for="pf-sku">SKU</label>
          <input class="input" id="pf-sku" value="${value('sku')}" maxlength="40">
        </div>
        <div class="field">
          <label for="pf-badge">Badge</label>
          <input class="input" id="pf-badge" value="${value('badge')}" placeholder="Bestseller, Deal of the day…" maxlength="24">
        </div>
        <div class="field">
          <label for="pf-delivery">Delivery days</label>
          <input class="input" id="pf-delivery" type="number" min="1" max="15" value="${value('delivery_days', 3)}">
        </div>
        <div class="field">
          <label for="pf-return">Return window (days)</label>
          <input class="input" id="pf-return" type="number" min="0" max="30" value="${value('return_days', 7)}">
        </div>
        <div class="field">
          <label for="pf-warranty">Warranty</label>
          <input class="input" id="pf-warranty" value="${value('warranty')}" placeholder="1 year manufacturer warranty">
        </div>
      </div>
      <div class="field">
        <label for="pf-image">Image URL</label>
        <input class="input" id="pf-image" value="${value('image_url')}" placeholder="https://images.unsplash.com/…">
      </div>
      <div class="field">
        <label for="pf-highlights">Highlights (one per line)</label>
        <textarea class="textarea" id="pf-highlights">${escapeHtml((product.highlights || []).join('\n'))}</textarea>
      </div>
      <div class="field">
        <label for="pf-description">Description</label>
        <textarea class="textarea" id="pf-description">${value('description')}</textarea>
      </div>
      <div class="pill-row">
        <label class="chip"><input type="checkbox" id="pf-active" ${product.is_active === false ? '' : 'checked'}> Active</label>
        <label class="chip"><input type="checkbox" id="pf-featured" ${product.is_featured ? 'checked' : ''}> Featured</label>
        <label class="chip"><input type="checkbox" id="pf-cod" ${product.cod_available === false ? '' : 'checked'}> COD available</label>
        <label class="chip"><input type="checkbox" id="pf-free" ${product.free_delivery ? 'checked' : ''}> Free delivery</label>
      </div>
    </form>`;
}

function readForm() {
  const highlights = $('pf-highlights').value.split('\n').map((line) => line.trim()).filter(Boolean);
  const body = {
    name: $('pf-name').value.trim(),
    category: Number($('pf-category').value) || null,
    brand: Number($('pf-brand').value) || null,
    price: $('pf-price').value,
    mrp: $('pf-mrp').value || $('pf-price').value,
    stock: Number($('pf-stock').value || 0),
    sku: $('pf-sku').value.trim(),
    badge: $('pf-badge').value.trim(),
    delivery_days: Number($('pf-delivery').value || 3),
    return_days: Number($('pf-return').value || 7),
    warranty: $('pf-warranty').value.trim(),
    image_url: $('pf-image').value.trim(),
    highlights,
    description: $('pf-description').value.trim(),
    is_active: $('pf-active').checked,
    is_featured: $('pf-featured').checked,
    cod_available: $('pf-cod').checked,
    free_delivery: $('pf-free').checked,
  };
  if (!body.name) throw new Error('Give the product a name.');
  if (!body.category) throw new Error('Choose a category.');
  if (!(Number(body.price) > 0)) throw new Error('Selling price must be greater than zero.');
  if (Number(body.mrp) < Number(body.price)) throw new Error('MRP cannot be below the selling price.');
  return body;
}

async function openEditor(id = null) {
  let product = {};
  if (id) {
    try {
      const detail = await api.product(id);
      product = detail.product;
    } catch (error) {
      toast(error.message, 'error');
      return;
    }
  }

  openModal({
    title: id ? `Edit — ${product.name}` : 'Add a new product',
    wide: true,
    body: formHtml(product),
    footer: `
      <button class="btn" type="button" data-cancel>Cancel</button>
      <button class="btn btn-primary" type="button" data-save>${id ? 'Save changes' : 'Create product'}</button>`,
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
          if (id) {
            await api.updateProduct(id, body);
            toast('Product updated — cached catalogue invalidated.', 'success');
          } else {
            await api.createProduct(body);
            toast('Product created and live on the storefront.', 'success');
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

/* -------------------------------------------------------------------- wires */

$('products-table').addEventListener('click', async (event) => {
  const plus = event.target.closest('[data-stock-plus]');
  const minus = event.target.closest('[data-stock-minus]');
  const toggle = event.target.closest('[data-toggle]');
  const edit = event.target.closest('[data-edit]');
  const remove = event.target.closest('[data-delete]');

  if (plus || minus) {
    const id = Number((plus || minus).dataset[plus ? 'stockPlus' : 'stockMinus']);
    const product = payload.results.find((row) => row.id === id);
    if (!product) return;
    const delta = plus ? 5 : -1;
    const next = Math.max(0, Number(product.stock) + delta);
    await patchProduct(id, { stock: next }, `${product.name}: stock set to ${next}.`);
    return;
  }

  if (toggle) {
    const id = Number(toggle.dataset.toggle);
    const product = payload.results.find((row) => row.id === id);
    if (!product) return;
    const nextActive = !product.is_active;
    await patchProduct(id, { is_active: nextActive },
      nextActive ? `${product.name} is live again.` : `${product.name} hidden from the storefront.`);
    return;
  }

  if (edit) {
    openEditor(Number(edit.dataset.edit));
    return;
  }

  if (remove) {
    const id = Number(remove.dataset.delete);
    const product = payload.results.find((row) => row.id === id);
    if (!product) return;
    const ok = await confirmDialog({
      title: `Delete ${product.name}?`,
      message: 'Products that appear in past orders cannot be deleted — deactivate them instead.',
      confirmLabel: 'Delete product',
      danger: true,
    });
    if (!ok) return;
    try {
      const result = await api.deleteProduct(id);
      toast(result.message, 'success');
      await load();
    } catch (error) {
      toast(error.message, 'error');
    }
  }
});

$('product-pagination').addEventListener('click', (event) => {
  const button = event.target.closest('[data-page]');
  if (!button) return;
  state.page = Number(button.dataset.page);
  load();
});

$('product-search-form').addEventListener('submit', (event) => {
  event.preventDefault();
  state.search = $('product-search').value.trim();
  state.page = 1;
  load();
});

$('product-category').addEventListener('change', (event) => {
  state.category = event.target.value;
  state.page = 1;
  load();
});

$('product-sort').addEventListener('change', (event) => {
  state.ordering = event.target.value;
  state.page = 1;
  load();
});

$('product-low').addEventListener('change', (event) => {
  state.low = event.target.checked;
  $('low-stock-chip').classList.toggle('is-on', state.low);
  render();
  syncUrl();
});

$('product-inactive').addEventListener('change', (event) => {
  state.inactive = event.target.checked;
  $('inactive-chip').classList.toggle('is-on', state.inactive);
  load();
});

$('add-product').addEventListener('click', () => openEditor());

/* --------------------------------------------------------------------- boot */

await sessionReady;
if (!session.authenticated) {
  location.assign(`/login/?next=${encodeURIComponent(location.pathname)}`);
} else if (!session.user.is_store_admin) {
  location.assign('/');
} else {
  try {
    [brands, categories] = await Promise.all([api.brands(), api.categories()]);
    $('product-category').insertAdjacentHTML('beforeend', categories
      .map((row) => `<option value="${row.id}">${escapeHtml(row.name)}</option>`).join(''));
    $('product-category').value = state.category;
    $('product-sort').value = state.ordering;
    $('product-search').value = state.search;
    $('product-inactive').checked = state.inactive;
    $('product-low').checked = state.low;
    $('low-stock-chip').classList.toggle('is-on', state.low);
    $('inactive-chip').classList.add('is-on');
  } catch (error) {
    toast(error.message, 'error');
  }
  await load();
}
