/** Login and registration (both pages share this module). */

import { api, escapeHtml, toast } from './api.js';

const params = new URLSearchParams(window.location.search);
const nextUrl = params.get('next');
const safeNext = nextUrl && nextUrl.startsWith('/') && !nextUrl.startsWith('//') ? nextUrl : null;

const DEMO = {
  demo: { username: 'demo', password: 'Demo@12345' },
  manager: { username: 'manager', password: 'Manager@123' },
  admin: { username: 'admin', password: 'Admin@12345' },
};

function showError(message) {
  const box = document.getElementById('form-error');
  if (!box) return;
  box.textContent = message;
  box.classList.toggle('hidden', !message);
}

function setBusy(button, busy) {
  button.disabled = busy;
  button.classList.toggle('is-loading', busy);
}

/** Turn a DRF 400 payload into the first human-readable string. */
function firstError(error) {
  const data = error.data;
  if (!data) return error.message;
  if (typeof data === 'string') return data;
  if (Array.isArray(data)) return String(data[0]);
  if (data.detail) return Array.isArray(data.detail) ? String(data.detail[0]) : String(data.detail);
  const key = Object.keys(data)[0];
  if (!key) return error.message;
  const value = data[key];
  const text = Array.isArray(value) ? value[0] : value;
  const label = key.replace(/_/g, ' ');
  return `${label.charAt(0).toUpperCase()}${label.slice(1)}: ${text}`;
}

function redirectAfterAuth(user) {
  const target = safeNext || (user && user.is_store_admin ? '/manage/' : '/');
  window.location.assign(target);
}

/* ------------------------------------------------------------------ login */

const loginForm = document.getElementById('login-form');
if (loginForm) {
  loginForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    showError('');
    const button = document.getElementById('submit-btn');
    const username = document.getElementById('username').value.trim();
    const password = document.getElementById('password').value;

    if (!username || !password) {
      showError('Enter both your username and password.');
      return;
    }

    setBusy(button, true);
    try {
      const data = await api.login({ username, password });
      toast(`Signed in as ${data.user.display_name || data.user.username}.`, 'success');
      redirectAfterAuth(data.user);
    } catch (error) {
      showError(firstError(error));
      setBusy(button, false);
    }
  });

  document.querySelectorAll('[data-demo]').forEach((button) => {
    button.addEventListener('click', () => {
      const account = DEMO[button.dataset.demo] || DEMO.demo;
      document.getElementById('username').value = account.username;
      document.getElementById('password').value = account.password;
      showError('');
      document.getElementById('submit-btn').focus();
    });
  });
}

/* --------------------------------------------------------------- register */

const registerForm = document.getElementById('register-form');
if (registerForm) {
  const read = (id) => (document.getElementById(id)?.value || '').trim();

  /* Indian mobile numbers are 10 digits starting 6-9: strip +91 / spaces as typed. */
  const phoneInput = document.getElementById('phone');
  phoneInput?.addEventListener('input', () => {
    const digits = phoneInput.value.replace(/\D/g, '').replace(/^0+/, '').slice(-10);
    phoneInput.value = digits;
  });

  registerForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    showError('');
    const button = document.getElementById('submit-btn');
    const payload = {
      username: read('username'),
      email: read('email'),
      first_name: read('first_name'),
      last_name: read('last_name'),
      phone: read('phone'),
      password: document.getElementById('password').value,
      password_confirm: document.getElementById('password_confirm').value,
    };

    if (!payload.username) {
      showError('Choose a username.');
      return;
    }
    if (payload.password.length < 8) {
      showError('Password must be at least 8 characters long.');
      return;
    }
    if (payload.password !== payload.password_confirm) {
      showError('The two passwords do not match.');
      return;
    }

    setBusy(button, true);
    try {
      const data = await api.register(payload);
      toast(`Welcome to BazaarNoon, ${escapeHtml(data.user.display_name || data.user.username)}!`, 'success');
      redirectAfterAuth(data.user);
    } catch (error) {
      showError(firstError(error));
      setBusy(button, false);
    }
  });
}
