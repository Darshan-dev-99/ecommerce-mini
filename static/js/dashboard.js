/** Seller dashboard: KPIs, 14-day revenue chart, live pulse and inventory alerts. */

import {
  api, money, plain, escapeHtml, thumb, statusClass, timeAgo, formatDate, toast, sessionReady, session,
} from './api.js';

const $ = (id) => document.getElementById(id);

let lastPulseSignature = '';

/* --------------------------------------------------------------- rendering */

function kpi(label, value, note = '', accent = false) {
  return `
    <div class="kpi${accent ? ' accent' : ''}">
      <span class="label">${escapeHtml(label)}</span>
      <span class="value">${value}</span>
      ${note ? `<span class="delta">${escapeHtml(note)}</span>` : ''}
    </div>`;
}

function renderKpis(kpis) {
  $('kpi-grid').innerHTML = [
    kpi('Revenue', money(kpis.revenue), 'Excludes cancelled orders', true),
    kpi('Orders', plain(kpis.orders), `${kpis.pending_fulfilment} awaiting fulfilment`),
    kpi('Avg order value', money(kpis.average_order_value), `${plain(kpis.units_sold)} units sold`),
    kpi('Delivered', plain(kpis.delivered), `${kpis.cancellation_rate}% cancellation rate`),
    kpi('Open returns', plain(kpis.returns_open), 'Awaiting approval'),
    kpi('Low stock', plain(kpis.low_stock), 'Fewer than 6 units'),
    kpi('Customers', plain(kpis.customers), 'Registered shoppers'),
    kpi('Live coupons', plain(kpis.active_coupons), 'Redeemable right now'),
  ].join('');
}

function renderChart(series) {
  const max = Math.max(...series.map((row) => Number(row.revenue)), 1);
  const total = series.reduce((sum, row) => sum + Number(row.revenue), 0);
  $('chart-total').textContent = `${money(total)} in the last 14 days`;

  $('revenue-chart').innerHTML = series.map((row, index) => {
    const height = Math.max(2, Math.round((Number(row.revenue) / max) * 100));
    const label = index % 2 === 0 || index === series.length - 1 ? row.label : '';
    return `
      <div class="bar-col" title="${escapeHtml(row.label)} · ${money(row.revenue)} · ${row.orders} orders">
        <i style="height:${height}%"></i>
        <span>${escapeHtml(label)}</span>
      </div>`;
  }).join('');
}

function renderStatus(counts) {
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0) || 1;
  $('status-breakdown').innerHTML = Object.entries(counts)
    .filter(([, count]) => count > 0)
    .map(([status, count]) => `
      <div class="bar-row" style="margin-bottom:8px">
        <span style="width:112px" class="status-chip status-${statusClass(status)}">${escapeHtml(status)}</span>
        <span class="bar"><i style="width:${Math.round((count / total) * 100)}%;background:${
          status === 'Cancelled' ? '#d32f2f' : status === 'Delivered' ? '#388e3c' : '#2874f0'}"></i></span>
        <b style="color:#0f172a;font-size:12px;width:26px;text-align:right">${count}</b>
      </div>`)
    .join('') || '<p class="muted small">No orders yet.</p>';
}

function renderRecent(orders) {
  const body = document.querySelector('#recent-orders tbody');
  if (!orders.length) {
    body.innerHTML = '<tr><td colspan="6" class="muted">No orders yet.</td></tr>';
    return;
  }
  body.innerHTML = orders.map((order) => `
    <tr>
      <td><a class="link" href="/orders/${order.id}/">${escapeHtml(order.order_number)}</a>
        <div class="small muted">${order.item_count} item${order.item_count > 1 ? 's' : ''}</div></td>
      <td>${escapeHtml(order.customer)}</td>
      <td class="small muted">${timeAgo(order.created_at)}</td>
      <td class="small">${escapeHtml(order.payment_method)}</td>
      <td class="num">${money(order.total_amount)}</td>
      <td><span class="status-chip status-${statusClass(order.status)}">${escapeHtml(order.status)}</span></td>
    </tr>`).join('');
}

function renderLowStock(rows) {
  $('low-stock').innerHTML = rows.length
    ? rows.map((row) => `
      <div class="low-stock">
        <a class="link" href="/manage/products/?q=${encodeURIComponent(row.name)}">${escapeHtml(row.name)}</a>
        <span class="stock-pill">${row.stock} left</span>
      </div>`).join('')
    : '<p class="muted small">Every active product has healthy stock.</p>';
}

function renderTop(rows) {
  $('top-products').innerHTML = rows.length
    ? rows.map((row) => `
      <div class="low-stock" style="gap:12px">
        ${thumb(row.image_url, row.name)}
        <div style="min-width:0">
          <a class="link clamp-2" href="/p/${encodeURIComponent(row.slug)}/">${escapeHtml(row.name)}</a>
          <div class="small muted">${money(row.price)} · ${plain(row.sold_count)} sold</div>
        </div>
      </div>`).join('')
    : '<p class="muted small">No sales recorded yet.</p>';
}

function renderCustomers(rows) {
  $('customer-count').textContent = `${rows.length} shoppers`;
  const body = document.querySelector('#customers tbody');
  body.innerHTML = rows.length
    ? rows.slice(0, 8).map((row) => `
      <tr>
        <td><b>${escapeHtml(row.display_name)}</b><div class="small muted">@${escapeHtml(row.username)}</div></td>
        <td class="small muted">${escapeHtml(row.email || '—')}<br>${escapeHtml(row.phone || '')}</td>
        <td class="small muted">${formatDate(row.date_joined)}</td>
        <td class="num">${row.order_count}</td>
        <td class="num">${money(row.spend)}</td>
      </tr>`).join('')
    : '<tr><td colspan="5" class="muted">No customers yet.</td></tr>';
}

/* -------------------------------------------------------------- live pulse */

function renderFeed(pulse) {
  $('pulse-active').textContent = plain(pulse.active);
  $('pulse-latest').textContent = pulse.latest
    ? `${pulse.latest.order_number} · ${pulse.latest.status}`
    : '—';
  $('pulse-stamp').textContent = `Synced ${new Date(pulse.server_time).toLocaleTimeString('en-IN')}`;

  const feed = $('pulse-feed');
  if (!pulse.new_orders.length) {
    feed.innerHTML = '<p class="muted small">No orders yet today.</p>';
    return;
  }
  feed.innerHTML = pulse.new_orders.map((order) => `
    <div class="low-stock" style="gap:8px">
      <span class="status-chip status-${statusClass(order.status)}">${escapeHtml(order.status)}</span>
      <a class="link" href="/orders/${order.id}/">${escapeHtml(order.order_number)}</a>
      <span class="small muted">${escapeHtml(order.customer)}</span>
      <span class="small muted" style="margin-left:auto">${timeAgo(order.created_at)}</span>
    </div>`).join('');

  const signature = pulse.new_orders.map((order) => `${order.id}:${order.status}`).join('|');
  if (lastPulseSignature && signature !== lastPulseSignature) {
    toast('Order activity just came in.', 'info');
  }
  lastPulseSignature = signature;
}

async function pollPulse() {
  try {
    renderFeed(await api.adminOverview());
  } catch {
    $('pulse-chip').classList.add('off');
  }
}

/* ------------------------------------------------------------------- load */

async function load(showToast = false) {
  try {
    const [data, customers] = await Promise.all([api.dashboard(), api.customers()]);
    renderKpis(data.kpis);
    renderChart(data.revenue_series);
    renderStatus(data.status_counts);
    renderRecent(data.recent_orders);
    renderLowStock(data.low_stock);
    renderTop(data.top_products);
    renderCustomers(customers.results);
    $('dash-sub').textContent =
      `Snapshot generated ${new Date(data.generated_at).toLocaleString('en-IN')} · served from cache when warm`;
    if (showToast) toast('Dashboard refreshed.', 'success');
  } catch (error) {
    $('dash-sub').textContent = error.message;
    toast(error.message, 'error');
  }
}

/* ------------------------------------------------------------------- boot */

await sessionReady;
if (!session.authenticated) {
  location.assign(`/login/?next=${encodeURIComponent(location.pathname)}`);
} else if (!session.user.is_store_admin) {
  location.assign('/');
} else {
  await load();
  await pollPulse();
  setInterval(pollPulse, 15000);
  setInterval(() => load(false), 60000);
  $('dash-refresh').addEventListener('click', () => load(true));
}
