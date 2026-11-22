/** Product detail page: gallery, buybox, pincode promise, reviews, related. */

import {
  api, money, plain, escapeHtml, stars, ratingPill, productCard, toast, openModal,
  session, isWishlisted, refreshCartCount, requireAuth, formatDate,
} from './api.js';

const slug = window.PRODUCT_SLUG;
const root = document.getElementById('product-root');
const extra = document.getElementById('product-extra');
const crumb = document.getElementById('crumb');

let product = null;
let quantity = 1;

const imageList = (item) => {
  const urls = [item.image_url, ...(item.images || []).map((image) => image.url)].filter(Boolean);
  return [...new Set(urls)].slice(0, 6);
};

function galleryHtml(item) {
  const images = imageList(item);
  if (!images.length) {
    return `<div class="gallery"><div class="gallery-main"><div class="fallback" style="font-size:64px;color:#cfd8e3">
      ${escapeHtml(item.name.charAt(0))}</div></div></div>`;
  }
  return `
    <div class="gallery">
      <div class="gallery-thumbs">
        ${images.map((url, index) => `
          <button type="button" class="${index ? '' : 'is-on'}" data-shot="${index}" aria-label="Image ${index + 1}">
            <img src="${escapeHtml(url)}" alt="" loading="lazy">
          </button>`).join('')}
      </div>
      <div>
        <div class="gallery-main"><img id="gallery-img" src="${escapeHtml(images[0])}" alt="${escapeHtml(item.name)}"></div>
        <div class="gallery-actions">
          <button class="btn btn-cart" type="button" data-add><svg width="16" height="16" viewBox="0 0 24 24"><path d="M3 4h2.2l2.2 10.4A2 2 0 0 0 9.6 16h8.2a2 2 0 0 0 2-1.6L21 7H6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="10" cy="20" r="1.4" fill="currentColor"/><circle cx="18" cy="20" r="1.4" fill="currentColor"/></svg> Add to cart</button>
          <button class="btn btn-buy" type="button" data-buy>Buy now</button>
        </div>
      </div>
    </div>`;
}

function buyboxHtml(item) {
  const off = Number(item.discount_percent || 0);
  const available = item.in_stock && item.is_active;
  const wished = isWishlisted(item.id) ? 'is-on' : '';
  const eta = new Date(Date.now() + item.delivery_days * 86400000);
  return `
    <aside class="buybox">
      <div class="brand-line">${escapeHtml(item.brand_name || '')}</div>
      <h1>${escapeHtml(item.name)}</h1>
      <div class="p-rating-row" style="margin-top:8px">
        ${ratingPill(item)}
        <span class="muted small">${plain(item.rating_count)} ratings · ${plain(item.review_count || 0)} reviews</span>
        ${item.sold_count ? `<span class="muted small">· ${plain(item.sold_count)}+ bought</span>` : ''}
      </div>

      <div class="price-block">
        <span class="now">${money(item.price)}</span>
        ${off > 0 ? `<span class="mrp">${money(item.mrp)}</span><span class="off">${off}% off</span>` : ''}
      </div>
      <p class="tax-note">Inclusive of all taxes · GST ${money(item.gst_amount || 0)} included
        ${off > 0 ? `· You save ${money(item.saving)}` : ''}</p>

      <div class="offer-strip" style="margin-top:12px">
        <div class="offer-line"><span class="ico">🏷️</span><span><b>Bank offer:</b> 10% instant discount on HDFC Bank cards, up to ₹1,500</span></div>
        <div class="offer-line"><span class="ico">💳</span><span><b>No cost EMI</b> from ${money(Math.max(499, Math.round(Number(item.price) / 6)))}/month</span></div>
        <div class="offer-line"><span class="ico">🎁</span><span>Use coupon codes at checkout for extra savings</span></div>
      </div>

      <div class="stock-line">
        ${available
          ? `<span class="badge green">In stock</span><span class="muted small">${item.stock <= 5 ? `Hurry — only ${item.stock} left` : `${plain(item.stock)} units ready to ship`}</span>`
          : '<span class="badge red">Out of stock</span><span class="muted small">Notify us and we will restock soon</span>'}
      </div>

      <div class="qty-line">
        <div class="stepper">
          <button type="button" data-qty="-1" ${quantity <= 1 ? 'disabled' : ''}>−</button>
          <span id="qty">${quantity}</span>
          <button type="button" data-qty="1" ${available && quantity < item.stock ? '' : 'disabled'}>+</button>
        </div>
        <span class="muted small">Maximum ${item.stock} per order</span>
      </div>

      <div class="gallery-actions" style="grid-template-columns:1fr 1fr">
        <button class="btn btn-cart btn-lg" type="button" data-add ${available ? '' : 'disabled'}>Add to cart</button>
        <button class="btn btn-buy btn-lg" type="button" data-buy ${available ? '' : 'disabled'}>Buy now</button>
      </div>
      <button class="btn btn-block btn-sm ${wished}" type="button" data-wish="${item.id}"
        style="margin-top:10px">♥ ${wished ? 'Saved to wishlist' : 'Save to wishlist'}</button>

      <div class="delivery-box">
        <b class="small">Delivery options</b>
        <form id="pin-form">
          <input id="pin-input" inputmode="numeric" maxlength="6" placeholder="Enter 6 digit pincode" aria-label="Pincode">
          <button class="btn btn-sm btn-outline" type="submit">Check</button>
        </form>
        <div class="delivery-result" id="pin-result">
          <span class="muted">Free delivery by <b>${eta.toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short' })}</b> · ${item.cod_available ? 'Cash on Delivery available' : 'Prepaid only'}</span>
        </div>
      </div>

      <div class="seller-row">
        <span class="badge blue">BazaarNoon Assured</span>
        <span>Sold by <b>BazaarNoon Retail</b> · ${item.warranty || 'Brand warranty'}</span>
      </div>

      <div class="assurance">
        <div><span class="ico">↺</span><b>${item.return_days || 7} day returns</b><span>Free pickup</span></div>
        <div><span class="ico">🚚</span><b>${item.free_delivery ? 'Free delivery' : 'Fast delivery'}</b><span>${item.delivery_days} day${item.delivery_days > 1 ? 's' : ''} to most pincodes</span></div>
        <div><span class="ico">🛡️</span><b>Genuine product</b><span>GST invoice included</span></div>
      </div>
    </aside>`;
}

function detailsHtml(item) {
  const highlights = (item.highlights || []).map((line) => `<li>${escapeHtml(line)}</li>`).join('');
  return `
    <section class="card pad section-gap" id="sec-details">
      <div class="pdp-tabs">
        <button class="pdp-tab is-on" type="button" data-anchor="sec-details">Highlights</button>
        <button class="pdp-tab" type="button" data-anchor="sec-specs">Specifications</button>
        <button class="pdp-tab" type="button" data-anchor="sec-reviews">Reviews</button>
      </div>
      <div class="grid-2">
        <div>
          <h2 style="font-size:16px;margin-bottom:10px">Product description</h2>
          <p class="muted" style="font-size:13.5px;line-height:1.65">${escapeHtml(item.description || '')}</p>
        </div>
        <div>
          <h2 style="font-size:16px;margin-bottom:10px">Highlights</h2>
          <ul class="highlights">${highlights || '<li>Details coming soon</li>'}</ul>
        </div>
      </div>
    </section>

    <section class="card pad section-gap" id="sec-specs">
      <h2 style="font-size:16px;margin-bottom:14px">Specifications</h2>
      <div class="spec-grid">
        <div class="spec-row"><b>Brand</b><span>${escapeHtml(item.brand_name || '—')}</span></div>
        <div class="spec-row"><b>Category</b><span>${escapeHtml(item.category_name || '—')}</span></div>
        <div class="spec-row"><b>SKU</b><span>${escapeHtml(item.sku || '—')}</span></div>
        <div class="spec-row"><b>Warranty</b><span>${escapeHtml(item.warranty || 'Brand warranty')}</span></div>
        <div class="spec-row"><b>Return window</b><span>${item.return_days} days from delivery</span></div>
        <div class="spec-row"><b>Delivery</b><span>${item.delivery_days} day${item.delivery_days > 1 ? 's' : ''} · ${item.free_delivery ? 'free' : '₹49 below ₹499'}</span></div>
        <div class="spec-row"><b>Payment</b><span>${item.cod_available ? 'UPI, cards, net banking, EMI, COD' : 'UPI, cards, net banking, EMI'}</span></div>
        <div class="spec-row"><b>GST included</b><span>${money(item.gst_amount || 0)} (18%)</span></div>
        <div class="spec-row"><b>Listed</b><span>${formatDate(item.created_at)}</span></div>
      </div>
    </section>

    <section class="card pad section-gap" id="sec-reviews">
      <div class="section-head">
        <h2 style="font-size:16px">Ratings &amp; reviews</h2>
        <button class="btn btn-sm btn-outline" type="button" id="write-review">Write a review</button>
      </div>
      <div id="rating-block"><div class="skeleton sk-line" style="width:60%"></div></div>
      <div id="review-list"></div>
    </section>`;
}

function ratingSummaryHtml(item, data) {
  const breakdown = item.rating_breakdown || {};
  return `
    <div class="rating-summary">
      <div class="big-rating">
        <span class="value">${Number(data.average || 0).toFixed(1)}<span class="muted" style="font-size:16px">★</span></span>
        ${stars(data.average)}
        <span class="muted small">${plain(data.count)} verified ratings</span>
      </div>
      <div class="stack" style="gap:6px">
        ${['5', '4', '3', '2', '1'].map((star) => {
          const row = breakdown[star] || { count: 0, percent: 0 };
          return `<div class="bar-row"><span>${star}★</span>
            <span class="bar"><i style="width:${row.percent}%"></i></span>
            <span style="min-width:34px;text-align:right">${plain(row.count)}</span></div>`;
        }).join('')}
      </div>
    </div>`;
}

function reviewHtml(review) {
  return `
    <article class="review">
      <div class="review-head">
        <span class="rating-pill">${review.rating}<span class="star">★</span></span>
        <h4>${escapeHtml(review.title)}</h4>
        ${review.is_verified_purchase ? '<span class="verified">✓ Verified purchase</span>' : ''}
      </div>
      <p>${escapeHtml(review.body)}</p>
      <div class="who" style="margin-top:6px">${escapeHtml(review.user_display)} · ${formatDate(review.created_at)}</div>
    </article>`;
}

/* ---------------------------------------------------------------- actions */

async function addToCart(goToCheckout = false) {
  if (!session.authenticated) { requireAuth(); return; }
  if (!product) return;
  try {
    const result = await api.addToCart(product.id, quantity);
    toast(result.message, 'success');
    await refreshCartCount();
    if (goToCheckout) { window.location.href = '/checkout/'; return; }
    const cart = result.cart;
    if (cart && cart.item_count) document.getElementById('cart-count').textContent = cart.item_count;
  } catch (error) {
    toast(error.message, 'error');
  }
}

function bindPin() {
  const form = document.getElementById('pin-form');
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const code = document.getElementById('pin-input').value.trim();
    const host = document.getElementById('pin-result');
    if (code.length !== 6) { toast('Enter a valid 6 digit pincode', 'error'); return; }
    host.innerHTML = '<span class="muted">Checking serviceability…</span>';
    try {
      const data = await api.pincode(code);
      if (!data.serviceable) {
        host.innerHTML = `<span class="oos">${escapeHtml(data.message)}</span>`;
        return;
      }
      host.innerHTML = `
        <span class="badge green">Deliverable</span>
        <span>${escapeHtml(data.city)}, ${escapeHtml(data.state)} — arrives in ${data.eta_min_days}–${data.eta_max_days} days</span>
        <span class="muted small">${data.cod_available ? 'Cash on Delivery available' : 'Prepaid orders only for this pincode'}</span>`;
    } catch (error) {
      host.innerHTML = `<span class="oos">${escapeHtml(error.message)}</span>`;
    }
  });
}

function bindGallery(item) {
  const images = imageList(item);
  document.querySelectorAll('[data-shot]').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-shot]').forEach((other) => other.classList.remove('is-on'));
      button.classList.add('is-on');
      const img = document.getElementById('gallery-img');
      if (img && images[Number(button.dataset.shot)]) img.src = images[Number(button.dataset.shot)];
    });
  });
}

function bindQty() {
  document.querySelectorAll('[data-qty]').forEach((button) => {
    button.addEventListener('click', () => {
      quantity = Math.min(product.stock, Math.max(1, quantity + Number(button.dataset.qty)));
      document.getElementById('qty').textContent = quantity;
      document.querySelectorAll('[data-qty]').forEach((control) => {
        control.disabled = control.dataset.qty === '-1' ? quantity <= 1 : quantity >= product.stock;
      });
    });
  });
}

function bindReviews(item) {
  const write = document.getElementById('write-review');
  write.addEventListener('click', () => {
    if (!session.authenticated) { requireAuth(); return; }
    openModal({
      title: 'Write a review',
      body: `
        <form id="review-form">
          <div class="field"><label for="rv-rating">Your rating</label>
            <select id="rv-rating" required>
              <option value="5">5 ★ Excellent</option><option value="4">4 ★ Good</option>
              <option value="3">3 ★ Average</option><option value="2">2 ★ Poor</option>
              <option value="1">1 ★ Terrible</option>
            </select></div>
          <div class="field"><label for="rv-title">Review title</label>
            <input id="rv-title" maxlength="80" required placeholder="Great value for money"></div>
          <div class="field"><label for="rv-body">Your review</label>
            <textarea id="rv-body" minlength="10" maxlength="1200" required placeholder="What did you like or dislike?"></textarea></div>
          <div class="form-actions"><button class="btn btn-primary" type="submit">Post review</button></div>
        </form>`,
      onMount(el, close) {
        el.querySelector('#review-form').addEventListener('submit', async (event) => {
          event.preventDefault();
          try {
            await api.addReview(item.id, {
              rating: Number(el.querySelector('#rv-rating').value),
              title: el.querySelector('#rv-title').value,
              body: el.querySelector('#rv-body').value,
            });
            toast('Thanks! Your review is live.', 'success');
            close();
            loadReviews(item);
          } catch (error) {
            toast(error.message, 'error');
          }
        });
      },
    });
  });
}

async function loadReviews(item) {
  const block = document.getElementById('rating-block');
  const list = document.getElementById('review-list');
  try {
    const data = await api.reviews(item.id);
    block.innerHTML = ratingSummaryHtml(item, data);
    list.innerHTML = data.results.length
      ? data.results.map(reviewHtml).join('')
      : '<p class="muted" style="padding:16px 0">No written reviews yet — be the first to review this product.</p>';
  } catch (error) {
    block.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
    list.innerHTML = '';
  }
}

/* ------------------------------------------------------------------- boot */

(async () => {
  try {
    const data = await api.product(slug);
    product = data.product;
    document.title = `${product.name} — BazaarNoon`;
    crumb.innerHTML = `<a href="/">Home</a><span>›</span>
      <a href="/shop/">All products</a><span>›</span>
      <a href="/shop/?category=${encodeURIComponent(product.category_slug)}">${escapeHtml(product.category_name)}</a>
      <span>›</span><span>${escapeHtml(product.name)}</span>`;

    root.innerHTML = `<div class="pdp">${galleryHtml(product)}${buyboxHtml(product)}</div>`;
    extra.innerHTML = detailsHtml(product) +
      (data.related.length
        ? `<section class="rail-section"><div class="section-head"><h2>Similar products</h2>
             <a class="link" href="/shop/?category=${encodeURIComponent(product.category_slug)}">See all →</a></div>
           <div class="rail">${data.related.map((row) => productCard(row)).join('')}</div></section>`
        : '');

    bindGallery(product);
    bindQty();
    bindPin();
    bindReviews(product);
    loadReviews(product);

    document.querySelectorAll('[data-add]').forEach((button) => {
      button.addEventListener('click', () => addToCart(false));
    });
    document.querySelectorAll('[data-buy]').forEach((button) => {
      button.addEventListener('click', () => addToCart(true));
    });
    document.querySelectorAll('[data-anchor]').forEach((button) => {
      button.addEventListener('click', () => {
        document.querySelectorAll('[data-anchor]').forEach((other) => other.classList.remove('is-on'));
        button.classList.add('is-on');
        document.getElementById(button.dataset.anchor).scrollIntoView({ behavior: 'smooth', block: 'start' });
      });
    });
  } catch (error) {
    root.innerHTML = `<div class="card empty"><span class="ico">😕</span><h2>Product unavailable</h2>
      <p>${escapeHtml(error.message)}</p><a class="btn btn-primary" href="/shop/">Browse the catalogue</a></div>`;
  }
})();
