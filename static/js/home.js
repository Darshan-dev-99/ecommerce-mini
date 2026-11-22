/** Home page: hero rotation, category circles, live offer cards and deal rails. */

import {
  api, productCard, escapeHtml, money, plain, session, sessionReady, skeletons,
} from './api.js';

const SLIDES = [
  {
    eyebrow: '✦ Big Billion Days · 12–16 Nov',
    title: 'Festive sale on everything you love. <span>Up to 80% off.</span>',
    copy: 'Mobiles, laptops, fashion, furniture and daily essentials — free delivery above ₹499, easy 7 day returns and Cash on Delivery across 19,000+ pincodes.',
    label: 'Shop deals of the day',
    href: '/shop/?ordering=discount',
  },
  {
    eyebrow: '📱 New launches · Galaxy S24 series',
    title: 'Flagship phones with <span>bank offers up to ₹12,000</span>',
    copy: 'Instant discounts with HDFC and ICICI cards, no-cost EMI from ₹2,499/month and exchange bonus on your old device.',
    label: 'Explore mobiles',
    href: '/shop/?category=mobiles',
  },
  {
    eyebrow: '🏠 Home & kitchen carnival',
    title: 'Upgrade your kitchen <span>from ₹649</span>',
    copy: 'Cookware, mixers, storage and cleaning essentials from Prestige, Hawkins, Milton and more — delivered in 2 days.',
    label: 'Shop home & kitchen',
    href: '/shop/?category=home-kitchen',
  },
];

function startHero(products) {
  const eyebrow = document.getElementById('hero-eyebrow');
  const title = document.getElementById('hero-title');
  const copy = document.getElementById('hero-copy-line');
  const art = document.getElementById('hero-art');
  const dots = document.getElementById('hero-dots');
  if (!eyebrow || !title) return;

  const text = document.querySelector('.hero-cta a');
  let index = 0;
  dots.innerHTML = SLIDES.map((_, i) => `<button type="button" data-slide="${i}" class="${i ? '' : 'is-on'}" aria-label="Slide ${i + 1}"></button>`).join('');

  const paint = (next) => {
    index = (next + SLIDES.length) % SLIDES.length;
    const slide = SLIDES[index];
    eyebrow.textContent = slide.eyebrow;
    title.innerHTML = slide.title;
    copy.textContent = slide.copy;
    if (text) { text.textContent = slide.label; text.href = slide.href; }
    const product = products[index % Math.max(1, products.length)];
    if (art && product && product.image_url) {
      art.src = product.image_url;
      art.alt = product.name;
      art.hidden = false;
    }
    dots.querySelectorAll('button').forEach((dot, i) => dot.classList.toggle('is-on', i === index));
  };

  paint(0);
  dots.addEventListener('click', (event) => {
    const button = event.target.closest('[data-slide]');
    if (button) paint(Number(button.dataset.slide));
  });
  setInterval(() => paint(index + 1), 7000);
}

function renderCategories(rows) {
  const host = document.getElementById('home-categories');
  if (!host) return;
  host.innerHTML = rows.map((row) => `
    <a class="cat-circle" href="/shop/?category=${encodeURIComponent(row.slug)}">
      <span class="ico" aria-hidden="true">${escapeHtml(row.icon || '🛍️')}</span>
      <span>${escapeHtml(row.name)}</span>
    </a>`).join('') || '<p class="muted">Catalog coming soon.</p>';
}

function renderOffers(coupons) {
  const host = document.getElementById('home-offers');
  if (!host) return;
  if (!coupons.length) { host.innerHTML = ''; return; }
  host.innerHTML = coupons.slice(0, 3).map((coupon) => `
    <article class="offer-card">
      <h3>${coupon.discount_type === 'percent'
        ? `Extra ${Number(coupon.value)}% off`
        : `Flat ₹${Number(coupon.value)} off`}</h3>
      <p>${escapeHtml(coupon.description || `On orders above ${money(coupon.min_order_value)}`)}</p>
      <button class="offer-code" type="button" data-copy="${escapeHtml(coupon.code)}">${escapeHtml(coupon.code)} · copy</button>
    </article>`).join('');

  host.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy]');
    if (!button) return;
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.textContent = 'Copied ✓';
    } catch {
      button.textContent = button.dataset.copy;
    }
  });
}

function renderBrands(rows, stats) {
  const host = document.getElementById('home-brands');
  if (!host) return;
  const chips = rows.map((row) => `
    <a class="brand-pill" href="/shop/?brand=${encodeURIComponent(row.slug)}">${escapeHtml(row.name)}
      <span class="muted small">· ${row.product_count}</span></a>`).join('');
  host.innerHTML = `${chips}<a class="brand-pill" href="/shop/?ordering=popularity">+ ${plain(stats.brands)} brands</a>`;
}

function rail(title, subtitle, products, link) {
  if (!products || !products.length) return '';
  return `
    <section class="rail-section">
      <div class="section-head">
        <div><h2>${escapeHtml(title)}</h2><span class="inline-note">${escapeHtml(subtitle)}</span></div>
        <a class="link" href="${link}">See all →</a>
      </div>
      <div class="rail">${products.map((product) => productCard(product)).join('')}</div>
    </section>`;
}

function renderRails(rails) {
  const host = document.getElementById('home-rails');
  if (!host) return;
  host.innerHTML = [
    rail('Deals of the day', 'Handpicked discounts, refreshed every hour', rails.deals, '/shop/?ordering=discount'),
    rail('Bestsellers', 'Most ordered by shoppers across India', rails.bestsellers, '/shop/?ordering=popularity'),
    rail('Top rated', 'Rated 4★ and above by verified buyers', rails.top_rated, '/shop/?ordering=rating&min_rating=4'),
    rail('New arrivals', 'Freshly listed this season', rails.new_arrivals, '/shop/?ordering=newest'),
  ].join('');
}

async function renderRecentlyViewed() {
  if (!session.authenticated) return;
  try {
    const { results } = await api.recentlyViewed();
    if (!results.length) return;
    document.getElementById('recent-section').hidden = false;
    document.getElementById('recent-rail').innerHTML = results.map((product) => productCard(product, { compact: true })).join('');
  } catch { /* signed out mid-flight */ }
}

async function boot() {
  await sessionReady;
  const rails = document.getElementById('home-rails');
  if (rails) rails.innerHTML = `<section class="rail-section"><div class="grid-products">${skeletons(8)}</div></section>`;

  try {
    const [home, offers] = await Promise.all([api.home(), api.offers().catch(() => ({ results: [] }))]);
    startHero(home.rails.deals.length ? home.rails.deals : home.rails.bestsellers);
    renderCategories(home.categories);
    renderOffers(offers.results || []);
    renderBrands(home.brands, home.stats);
    renderRails(home.rails);
  } catch (error) {
    if (rails) rails.innerHTML = `<section class="rail-section"><p class="muted">Could not load the catalog: ${escapeHtml(error.message)}</p></section>`;
  }
  renderRecentlyViewed();
}

boot();
