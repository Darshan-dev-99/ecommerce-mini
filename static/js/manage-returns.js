/** Returns desk: approve, reject or refund customer return requests. */

import {
  api, money, escapeHtml, statusClass, formatDateTime, timeAgo,
  toast, confirmDialog, sessionReady, session,
} from './api.js';

const $ = (id) => document.getElementById(id);
const STATUSES = ['Requested', 'Approved', 'Rejected', 'Refunded'];
const state = { status: 'all' };
let rows = [];

const ACTIONS = {
  approve: { label: 'Approve pickup', confirm: 'Approve this return and schedule a pickup?' },
  reject: { label: 'Reject', confirm: 'Reject this return? The order goes back to Delivered.' },
  refund: { label: 'Refund', confirm: 'Mark this return refunded and restore stock?' },
};

function tabs(counts) {
  const total = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : rows.length;
  const items = [{ value: 'all', label: 'All', count: total }]
    .concat(STATUSES.map((status) => ({ value: status, label: status, count: (counts || {})[status] || 0 })));
  $('return-tabs').innerHTML = items.map((item) => `
    <button class="tab${state.status === item.value ? ' is-on' : ''}" type="button" data-status="${item.value}">
      ${escapeHtml(item.label)} <span style="opacity:.7">${item.count}</span>
    </button>`).join('');
}

function cardHtml(row) {
  const open = row.status === 'Requested' || row.status === 'Approved';
  return `
    <article class="card pad" data-row="${row.id}">
      <div class="row between" style="align-items:flex-start;flex-wrap:wrap;gap:10px">
        <div>
          <div class="row" style="gap:8px;flex-wrap:wrap">
            <a class="link" href="/orders/${row.order}/" target="_blank" rel="noopener">${escapeHtml(row.order_number)}</a>
            <span class="status-chip status-${statusClass(row.status)}">${escapeHtml(row.status)}</span>
            <span class="small muted">requested ${timeAgo(row.created_at)}</span>
          </div>
          <div class="small muted" style="margin-top:4px">${escapeHtml(row.customer || '')} · order ${money(row.order_total)} · delivered ${row.delivered_at ? formatDateTime(row.delivered_at) : '—'}</div>
        </div>
        <div class="small" style="text-align:right">
          <b>${escapeHtml(row.reason_display || row.reason)}</b>
          <div class="muted">Refund: ${row.refund_amount ? money(row.refund_amount) : 'pending assessment'}</div>
        </div>
      </div>

      ${row.comment ? `<p class="inline-note" style="margin-top:10px">“${escapeHtml(row.comment)}”</p>` : ''}
      ${row.admin_note ? `<p class="inline-note" style="margin-top:6px">Internal note: ${escapeHtml(row.admin_note)}</p>` : ''}
      ${row.resolved_at ? `<p class="small muted" style="margin-top:6px">Resolved ${formatDateTime(row.resolved_at)}</p>` : ''}

      ${open ? `
        <div class="toolbar" style="margin-top:12px">
          <input class="input grow" data-note="${row.id}" placeholder="Internal note (optional)" style="max-width:340px">
          ${Object.entries(ACTIONS).map(([action, meta]) => `
            <button class="btn btn-sm ${action === 'reject' ? '' : action === 'refund' ? 'btn-dark' : 'btn-primary'}"
              type="button" data-action="${action}" data-id="${row.id}">${meta.label}</button>`).join('')}
        </div>` : ''}
    </article>`;
}

function render(payload) {
  rows = payload.results;
  $('returns-sub').textContent = `${payload.count} return request${payload.count === 1 ? '' : 's'} shown · updated ${new Date().toLocaleTimeString('en-IN')}`;
  tabs(payload.status_counts);
  $('return-list').innerHTML = rows.length
    ? rows.map(cardHtml).join('')
    : '<div class="card pad"><p class="muted small">No return requests in this bucket.</p></div>';
}

async function load() {
  try {
    render(await api.returns({ status: state.status === 'all' ? '' : state.status }));
  } catch (error) {
    toast(error.message, 'error');
  }
}

$('return-tabs').addEventListener('click', (event) => {
  const tab = event.target.closest('[data-status]');
  if (!tab) return;
  state.status = tab.dataset.status;
  load();
});

$('return-list').addEventListener('click', async (event) => {
  const button = event.target.closest('[data-action]');
  if (!button) return;
  const action = button.dataset.action;
  const id = Number(button.dataset.id);
  const note = document.querySelector(`[data-note="${id}"]`)?.value || '';
  const meta = ACTIONS[action];

  const ok = await confirmDialog({
    title: meta.label,
    message: meta.confirm,
    confirmLabel: meta.label,
    danger: action === 'reject',
  });
  if (!ok) return;

  button.disabled = true;
  try {
    const result = await api.resolveReturn(id, { action, admin_note: note });
    toast(result.message, 'success');
    await load();
  } catch (error) {
    toast(error.message, 'error');
    button.disabled = false;
  }
});

$('returns-refresh').addEventListener('click', () => load());

await sessionReady;
if (!session.authenticated) {
  location.assign(`/login/?next=${encodeURIComponent(location.pathname)}`);
} else if (!session.user.is_store_admin) {
  location.assign('/');
} else {
  await load();
  setInterval(() => load(), 45000);
}
