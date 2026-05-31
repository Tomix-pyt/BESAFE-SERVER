// ─────────────────────────────────────────────────────────────
//  CONFIG — change BASE_URL to your Flask server address
// ─────────────────────────────────────────────────────────────
const BASE_URL = 'http://127.0.0.1:5000';

// ─────────────────────────────────────────────────────────────
//  UI HELPERS (UTILITIES)
// ─────────────────────────────────────────────────────────────
function showError(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.classList.add('visible');
    setTimeout(() => { el.classList.remove('visible'); }, 800);
}

function hideError(id) {
  const el = document.getElementById(id);
  el.classList.remove('visible');
}

function setLoading(btnId, loading) {
  const btn = document.getElementById(btnId);
  btn.disabled = loading;
  btn.textContent = loading ? 'Please wait…' : btn.dataset.label;
}

function showLogin() {
  document.getElementById('registerForm').style.display = 'none';
  document.getElementById('loginForm').style.display    = 'block';
}

function showRegister() {
  document.getElementById('loginForm').style.display    = 'none';
  document.getElementById('registerForm').style.display = 'block';
}

// ─────────────────────────────────────────────────────────────
//  LOGIN PART
// ─────────────────────────────────────────────────────────────
document.getElementById('btnLogin').dataset.label = 'Sign In';

document.getElementById('btnLogin').addEventListener('click', async () => {
  hideError('loginError');

  const email    = document.getElementById('loginEmail').value.trim();
  const password = document.getElementById('loginPassword').value;

  if (!email || !password) {
    showError('loginError', 'Please fill in all fields.');
    return;
  }

  setLoading('btnLogin', true);

  try {
    const res  = await fetch(`${BASE_URL}/auth/login`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, password })
    });
    const data = await res.json();

    if (!res.ok) {
      showError('loginError', data.error || 'Login failed.');
      return;
    }

    // Save to localStorage
    localStorage.setItem('besafe_token',  data.token);
    localStorage.setItem('besafe_agency', JSON.stringify(data.agency));

    // Redirect to dashboard
    // alert('Login OK, about to redirect to dashboard');
    window.location.href = '/dashboard';

  } catch (err) {
    showError('loginError', 'Cannot reach server. Check your connection.');
    console.error(err);
  } finally {
    setLoading('btnLogin', false);
  }
});

// Allow Enter key on password field
document.getElementById('loginPassword').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') document.getElementById('btnLogin').click();
});


// ─────────────────────────────────────────────────────────────
//  REGISTERATION PART
// ─────────────────────────────────────────────────────────────
document.getElementById('btnRegister').dataset.label = 'Register Agency';

document.getElementById('btnRegister').addEventListener('click', async () => {
  hideError('registerError');

  const name     = document.getElementById('regName').value.trim();
  const region   = document.getElementById('regRegion').value.trim();
  const phone    = document.getElementById('regPhone').value.trim();
  const email    = document.getElementById('regEmail').value.trim();
  const password = document.getElementById('regPassword').value;
  const confirm  = document.getElementById('regConfirm').value;
  const regLat   = parseFloat(document.getElementById('regLat').value);
  const regLng   = parseFloat(document.getElementById('regLng').value);

  if (!name || !region || !phone || !email || !password) {
    showError('registerError', 'All fields are required.');
    return;
  }
  if (password.length < 8) {
    showError('registerError', 'Password must be at least 8 characters.');
    return;
  }
  if (password !== confirm) {
    showError('registerError', 'Passwords do not match.');
    return;
  }

  setLoading('btnRegister', true);

  const body = { name, region, phone_number: phone, email, password };
  if (!isNaN(regLat) && !isNaN(regLng)) {
    body.location = { lat: regLat, lng: regLng };
  }

  try {
    const res  = await fetch(`${BASE_URL}/auth/register`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(body)
    });
    const data = await res.json();

    if (!res.ok) {
      showError('registerError', data.error || 'Registration failed.');
      return;
    }

    // Switch to login and show success hint
    showLogin();
    document.getElementById('loginEmail').value = email;
    document.getElementById('loginError').style.color = 'var(--low)';
    showError('loginError', '✓ Agency registered! Sign in to continue.');
    document.getElementById('loginError').style.color = '';

  } catch (err) {
    showError('registerError', 'Cannot reach server. Check your connection.');
    console.error(err);
  } finally {
    setLoading('btnRegister', false);
  }
});


// ─────────────────────────────────────────────────────────────
//  AUTO-REDIRECT if already logged in
// ─────────────────────────────────────────────────────────────
(async () => {
  const token = localStorage.getItem('besafe_token');
  if (!token) return;

  try {
    const res = await fetch(`${BASE_URL}/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      window.location.href = '/dashboard';
    } else {
      localStorage.removeItem('besafe_token');
      localStorage.removeItem('besafe_agency');
    }
  } catch (_) { /* server offline — stay on login */ }
})();
const params = new URLSearchParams(window.location.search);
if (params.get('register') === 'true') {
  window.showRegister();
}
