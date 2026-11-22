/** Shop page: server-driven filters, sorting and pagination kept in the URL. */

import {
  api, qs, productCard, skeletons, escapeHtml, plain, toast,
} from './api.js';

const grid = document.getElementById('shop-grid');
const pagination = document.getElementById('pagination');
const countEl = document.getElementById('result-count');
const appliedEl = document.getElementById('applied');
const titleEl = document.getElementById('shop-title');
const subEl = document.getElementById('shop-sub');

const state = {
  search: '',
  category: '',
  brand: '',
  min_price: '',
  max_price: '',
  min_rating: '',
  min_discount: '',
  in_stock: '',
  ordering: 'relevance',
  page: '1',
  ...qs.all(),
};

let categories = [];
let brands = [];
let controller = null;

const brandList = () => state.brand.split(',').filter(Boolean);

function syncUrl() {
  qs.set({
    search: state.search,
    category: state.category,
    brand: state.brand,
    min_price: state.min_price,
    max_price: state.max_price,
    min_rating: state.min_rating,
    min_discount: state.min_discount,
    in_stock: state.in_stock,
    ordering: state.ordering === 'relevance' ? '' : state.ordering,
    page: state.page === '1' ? '' : state.page,
  });
}

/* ------------------------------------------------------------- filter UI */

function paintFilters() {
  const currentCategory = state.category;

  document.getElementById('filter-categories').innerHTML = `
    <a class="check ${currentCategory ? '' : 'is-on'}" href="/shop/" data-category="">All categories</a>
    ${categories.map((row) => `
      <a class="check ${currentCategory === row.slug ? 'is-on' : ''}" href="/shop/?category=${row.slug}" data-category="${row.slug}"
         style="${currentCategory === row.slug ? 'color:var(--blue);font-weight:700' : ''}">
        ${escapeHtml(row.icon || '•')} ${escapeHtml(row.name)}
        <span class="muted small" style="margin-left:auto">${row.product_count || ''}</span>
      </a>`).join('')}`;

  document.getElementById('filter-brands').innerHTML = brands.map((row) => `
    <label class="check">
      <input type="checkbox" value="${row.slug}" ${brandList().includes(row.slug) ? 'checked' : ''}>
      <span>${escapeHtml(row.name)}</span>
      <span class="muted small" style="margin-left:auto">${row.product_count || ''}</span>
    </label>`).join('') || '<span class="muted small">No brands yet</span>';

  document.getElementById('filter-min').value = state.min_price;
  document.getElementById('filter-max').value = state.max_price;
  document.getElementById('filter-stock').checked = Boolean(state.in_stock);

  document.querySelectorAll('[data-rating]').forEach((button) => {
    button.classList.toggle('is-on', state.min_rating === button.dataset.rating);
  });
  document.querySelectorAll('[data-discount]').forEach((button) => {
    button.classList.toggle('is-on', state.min_discount === button.dataset.discount);
  });
  document.querySelectorAll('[data-sort]').forEach((button) => {
    button.classList.toggle('is-on', state.ordering === button.dataset.sort);
  });
}

function paintApplied() {
  const chips = [];
  const chip = (key, label, value = '') => chips.push(
    `<button class="chip is-on" type="button" data-clear="${key}" data-value="${escapeHtml(value)}">${label} ✕</button>`,
  );

  if (state.search) chip('search', `“${escapeHtml(state.search)}”`);
  if (state.category) {
    const row = categories.find((item) => item.slug === state.category);
    chip('category', `Category: ${escapeHtml(row ? row.name : state.category)}`);
  }
  brandList().forEach((slug) => {
    const row = brands.find((item) => item.slug === slug);
    chip('brand', `Brand: ${escapeHtml(row ? row.name : slug)}`, slug);
  });
  if (state.min_price || state.max_price) {
    chip('price', `Price: ₹${state.min_price || 0} – ₹${state.max_price || '∞'}`);
  }
  if (state.min_rating) chip('min_rating', `${state.min_rating}★ & above`);
  if (state.min_discount) chip('min_discount', `${state.min_discount}%+ off`);
  if (state.in_stock) chip('in_stock', 'In stock only');

  appliedEl.innerHTML = chips.length
    ? chips.join('') + '<button class="chip" type="button" data-clear="all">Clear all</button>'
    : '';
}

/* --------------------------------------------------------------- rendering */

function paintPagination(meta) {
  if (!meta || meta.pages <= 1) { pagination.innerHTML = ''; return; }
  const page = Number(meta.page);
  const windowStart = Math.max(1, Math.min(page - 2, meta.pages - 4));
  const numbers = [];
  for (let index = windowStart; index < windowStart + 5 && index <= meta.pages; index += 1) numbers.push(index);

  pagination.innerHTML = `
    <button class="page-btn" type="button" data-page="${page - 1}" ${page <= 1 ? 'disabled' : ''}>‹ Prev</button>
    ${windowStart > 1 ? '<button class="page-btn" type="button" data-page="1">1</button><span class="muted">…</span>' : ''}
    ${numbers.map((number) => `<button class="page-btn ${number === page ? 'is-on' : ''}" type="button" data-page="${number}">${number}</button>`).join('')}
    ${windowStart + 4 < meta.pages ? `<span class="muted">…</span><button class="page-btn" type="button" data-page="${meta.pages}">${meta.pages}</button>` : ''}
    <button class="page-btn" type="button" data-page="${page + 1}" ${meta.has_next ? '' : 'disabled'}>Next ›</button>`;
}

async function load() {
  paintFilters();
  paintApplied();
  syncUrl();

  const params = {};
  Object.entries(state).forEach(([key, value]) => { if (value && value !== 'all') params[key] = value; });
  params.page_size = 24;

  if (controller) controller.abort();
  controller = new AbortController();
  grid.innerHTML = skeletons(9);
  countEl.textContent = 'Loading…';
  titleEl.textContent = state.search ? `Results for “${state.search}”` : 'All products';
  subEl.textContent = 'Browse the full BazaarNoon catalogue — prices include GST.';

  try {
    const data = await api.products(params);
    grid.innerHTML = data.results.length
      ? data.results.map((product) => productCard(product)).join('')
      : `<div class="card empty" style="grid-column:1/-1">
           <span class="ico">🔍</span><h2>No products matched</h2>
           <p>Try removing a filter, or search for a different brand or category.</p>
           <a class="btn btn-primary" href="/shop/">Reset filters</a>
         </div>`;
    countEl.textContent = `Showing ${data.results.length} of ${plain(data.count)} product${data.count === 1 ? '' : 's'}`;
    paintPagination(data);
    if (data.results.length && state.category) {
      const row = categories.find((item) => item.slug === state.category);
      if (row) titleEl.textContent = row.name;
    }
    if (data.results.length && state.search) titleEl.textContent = `Results for “${state.search}”`;
  } catch (error) {
    if (error.name === 'AbortError') return;
    grid.innerHTML = `<div class="card empty" style="grid-column:1/-1"><h2>Could not load products</h2><p>${escapeHtml(error.message)}</p></div>`;
    countEl.textContent = '';
  }
}

/* ------------------------------------------------------------- listeners */

document.getElementById('filter-categories').addEventListener('click', (event) => {
  const link = event.target.closest('[data-category]');
  if (!link) return;
  event.preventDefault();
  state.category = link.dataset.category;
  state.page = '1';
  load();
});

document.getElementById('filter-brands').addEventListener('change', (event) => {
  const checkbox = event.target.closest('input[type="checkbox"]');
  if (!checkbox) return;
  const current = new Set(brandList());
  if (checkbox.checked) current.add(checkbox.value); else current.delete(checkbox.value);
  state.brand = [...current].join(',');
  state.page = '1';
  load();
});

document.getElementById('filter-price-apply').addEventListener('click', () => {
  state.min_price = document.getElementById('filter-min').value;
  state.max_price = document.getElementById('filter-max').value;
  state.page = '1';
  load();
});

document.getElementById('filter-rating').addEventListener('click', (event) => {
  const button = event.target.closest('[data-rating]');
  if (!button) return;
  state.min_rating = state.min_rating === button.dataset.rating ? '' : button.dataset.rating;
  state.page = '1';
  load();
});

document.getElementById('filter-discount').addEventListener('click', (event) => {
  const button = event.target.closest('[data-discount]');
  if (!button) return;
  state.min_discount = state.min_discount === button.dataset.discount ? '' : button.dataset.discount;
  state.page = '1';
  load();
});

document.getElementById('filter-stock').addEventListener('change', (event) => {
  state.in_stock = event.target.checked ? '1' : '';
  state.page = '1';
  load();
});

document.getElementById('filter-clear').addEventListener('click', () => {
  Object.assign(state, {
    search: '', category: '', brand: '', min_price: '', max_price: '',
    min_rating: '', min_discount: '', in_stock: '', page: '1',
  });
  document.getElementById('shop-search').value = '';
  load();
});

appliedEl.addEventListener('click', (event) => {
  const chip = event.target.closest('[data-clear]');
  if (!chip) return;
  const key = chip.dataset.clear;
  if (key === 'all') {
    Object.assign(state, {
      search: '', category: '', brand: '', min_price: '', max_price: '',
      min_rating: '', min_discount: '', in_stock: '', page: '1',
    });
    document.getElementById('shop-search').value = '';
  } else if (key === 'price') {
    state.min_price = ''; state.max_price = '';
  } else if (key === 'brand') {
    state.brand = brandList().filter((slug) => slug !== chip.dataset.value).join(',');
  } else {
    state[key] = '';
  }
  state.page = '1';
  load();
});

document.getElementById('sort-tabs').addEventListener('click', (event) => {
  const button = event.target.closest('[data-sort]');
  if (!button) return;
  state.ordering = button.dataset.sort;
  state.page = '1';
  load();
});

pagination.addEventListener('click', (event) => {
  const button = event.target.closest('[data-page]');
  if (!button || button.disabled) return;
  state.page = button.dataset.page;
  load();
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

document.getElementById('shop-search-form').addEventListener('submit', (event) => {
  event.preventDefault();
  state.search = document.getElementById('shop-search').value.trim();
  state.page = '1';
  load();
});

document.getElementById('shop-search').value = state.search;

/* ------------------------------------------------------------------ boot */

(async () => {
  try {
    [categories, brands] = await Promise.all([api.categories(), api.brands()]);
  } catch (error) {
    toast(`Filters unavailable: ${error.message}`, 'error');
  }
  load();
})();
