/** Account page: profile edits and saved address book. */

import {
  api, escapeHtml, toast, openModal, confirmDialog, session, sessionReady, initials,
} from './api.js';

const form = document.getElementById('profile-form');
const grid = document.getElementById('address-grid');

let addresses = [];

/* ----------------------------------------------------------------- profile */

function fillProfile() {
  const user = session.user || {};
  document.getElementById('acc-name').textContent = user.display_name || user.username || 'Guest';
  document.getElementById('acc-email').textContent = user.email || (user.phone ? `+91 ${user.phone}` : '');
  form.first_name.value = user.first_name || '';
  form.last_name.value = user.last_name || '';
  form.email.value = user.email || '';
  form.phone.value = user.phone || '';
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    const data = await api.updateProfile({
      first_name: form.first_name.value.trim(),
      last_name: form.last_name.value.trim(),
      email: form.email.value.trim(),
      phone: form.phone.value.trim(),
    });
    session.user = data.user || data;
    fillProfile();
    toast('Profile updated.', 'success');
  } catch (error) {
    toast(error.message, 'error');
  }
});

/* --------------------------------------------------------------- addresses */

function addressCard(address) {
  return `
    <article class="address-card ${address.is_default ? 'is-default' : ''}">
      <span class="tag">${escapeHtml(address.label)}${address.is_default ? ' · Default' : ''}</span>
      <b>${escapeHtml(address.full_name)}</b>
      <address>${escapeHtml(address.line1)}${address.line2 ? `, ${escapeHtml(address.line2)}` : ''}<br>
        ${escapeHtml(address.city)}, ${escapeHtml(address.state)} — ${address.pincode}<br>
        📞 ${escapeHtml(address.phone)}</address>
      <div class="actions">
        <button type="button" data-edit="${address.id}">Edit</button>
        ${address.is_default ? '' : `<button type="button" data-default="${address.id}">Set default</button>`}
        <button type="button" class="danger" data-delete="${address.id}">Delete</button>
      </div>
    </article>`;
}

async function loadAddresses() {
  try {
    addresses = await api.addresses();
    grid.innerHTML = addresses.length
      ? addresses.map(addressCard).join('')
      : `<div class="card empty" style="grid-column:1/-1"><span class="ico">📍</span>
           <h2 style="font-size:17px">No addresses saved</h2>
           <p>Add your home or office address for faster checkout.</p>
           <button class="btn btn-primary" type="button" data-add>Add address</button></div>`;
  } catch (error) {
    grid.innerHTML = `<p class="muted">${escapeHtml(error.message)}</p>`;
  }
}

function addressForm(address = null) {
  return `
    <form id="address-form">
      <div class="form-grid">
        <div class="field"><label>Label</label><select name="label">
          ${['Home', 'Work', 'Other'].map((label) => `<option ${address && address.label === label ? 'selected' : ''}>${label}</option>`).join('')}
        </select></div>
        <div class="field"><label>Full name</label><input name="full_name" required value="${address ? escapeHtml(address.full_name) : ''}"></div>
        <div class="field"><label>Mobile</label><input name="phone" required inputmode="numeric" maxlength="10" value="${address ? address.phone : ''}"></div>
        <div class="field"><label>Pincode</label><input name="pincode" required inputmode="numeric" maxlength="6" value="${address ? address.pincode : ''}"></div>
        <div class="field span-2"><label>House / street</label><input name="line1" required value="${address ? escapeHtml(address.line1) : ''}"></div>
        <div class="field span-2"><label>Area / landmark</label><input name="line2" value="${address ? escapeHtml(address.line2) : ''}"></div>
        <div class="field"><label>City</label><input name="city" required value="${address ? escapeHtml(address.city) : ''}"></div>
        <div class="field"><label>State</label><input name="state" required value="${address ? escapeHtml(address.state) : ''}"></div>
        <div class="field span-2"><label class="check"><input type="checkbox" name="is_default"
          ${address && address.is_default ? 'checked' : ''}> Use as my default delivery address</label></div>
      </div>
      <div class="form-actions"><button class="btn btn-primary" type="submit">Save address</button></div>
    </form>`;
}

function openAddress(address = null) {
  openModal({
    title: address ? 'Edit address' : 'Add address',
    body: addressForm(address),
    onMount(el, close) {
      el.querySelector('#address-form').addEventListener('submit', async (event) => {
        event.preventDefault();
        const data = new FormData(event.target);
        const body = Object.fromEntries(data.entries());
        body.is_default = data.has('is_default');
        try {
          if (address) await api.updateAddress(address.id, body);
          else await api.createAddress(body);
          toast('Address saved.', 'success');
          close();
          loadAddresses();
        } catch (error) {
          toast(error.message, 'error');
        }
      });
    },
  });
}

/* --------------------------------------------------------------- listeners */

grid.addEventListener('click', async (event) => {
  if (event.target.closest('[data-add]')) { openAddress(); return; }

  const edit = event.target.closest('[data-edit]');
  if (edit) {
    const row = addresses.find((address) => address.id === Number(edit.dataset.edit));
    if (row) openAddress(row);
    return;
  }

  const def = event.target.closest('[data-default]');
  if (def) {
    try {
      await api.updateAddress(Number(def.dataset.default), { is_default: true });
      toast('Default address updated.', 'success');
      loadAddresses();
    } catch (error) {
      toast(error.message, 'error');
    }
    return;
  }

  const del = event.target.closest('[data-delete]');
  if (del) {
    const row = addresses.find((address) => address.id === Number(del.dataset.delete));
    const okay = await confirmDialog({
      title: 'Delete address?',
      message: `Remove the ${row ? row.label.toLowerCase() : ''} address for ${row ? row.full_name : 'this contact'}?`,
      confirmLabel: 'Delete',
      danger: true,
    });
    if (!okay) return;
    try {
      await api.deleteAddress(Number(del.dataset.delete));
      toast('Address deleted.', 'success');
      loadAddresses();
    } catch (error) {
      toast(error.message, 'error');
    }
  }
});

document.getElementById('add-address').addEventListener('click', () => openAddress());

document.querySelectorAll('.account-nav a[data-nav-link]').forEach((link) => {
  link.addEventListener('click', () => {
    document.querySelectorAll('.account-nav a').forEach((other) => other.classList.remove('is-on'));
    link.classList.add('is-on');
  });
});

/* ------------------------------------------------------------------- boot */

(async () => {
  await sessionReady;
  fillProfile();
  loadAddresses();
  if (location.hash === '#addresses') document.getElementById('addresses').scrollIntoView({ behavior: 'smooth' });
  const badge = document.getElementById('acc-email');
  if (badge && session.user) badge.title = `Signed in as ${initials(session.user.display_name || session.user.username)}`;
})();
