// ─────────────────────────────────────────────────────────────
//  BASE_URL — empty = same origin (works in dev & production)
// ─────────────────────────────────────────────────────────────
const BASE_URL = '';

// ─────────────────────────────────────────────────────────────
//  UI HELPERS (UTILITIES)
// ─────────────────────────────────────────────────────────────
function showError(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.classList.add('visible');
    setTimeout(() => { el.classList.remove('visible'); }, 1000);
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
  setTimeout(updateRegSteps, 100);
}

window.showRegister = function () {
  document.getElementById('loginForm').style.display    = 'none';
  document.getElementById('registerForm').style.display = 'block';
  setTimeout(updateRegSteps, 100);
};

// ── Registration helpers ──

function togglePw() {
  const pw = document.getElementById('regPassword');
  const btn = document.getElementById('regPwToggle');
  if (pw.type === 'password') {
    pw.type = 'text';
    btn.textContent = '🙈';
  } else {
    pw.type = 'password';
    btn.textContent = '👁';
  }
}

function updateRegSteps() {
  const s1 = document.getElementById('regSection1');
  const s2 = document.getElementById('regSection2');
  const s3 = document.getElementById('regSection3');
  const steps = document.querySelectorAll('.reg-step-num');
  if (!steps.length) return;
  const filled1 = s1 ? Array.from(s1.querySelectorAll('input')).every(i => i.value.trim()) : false;
  const filled2 = s2 ? Array.from(s2.querySelectorAll('input')).every(i => i.value.trim()) : false;
  const hasLoc = !!document.getElementById('regLat').value;
  steps.forEach((el, i) => {
    el.classList.remove('active', 'done');
    if (i === 0 && filled1) el.classList.add('done');
    else if (i === 0) el.classList.add('active');
    if (i === 1 && filled2) el.classList.add('done');
    else if (i === 1 && filled1) el.classList.add('active');
    if (i === 2 && hasLoc) el.classList.add('done');
    else if (i === 2 && filled2) el.classList.add('active');
  });
  const fills = document.querySelectorAll('.reg-step-fill');
  if (fills[0]) fills[0].style.width = filled1 ? '100%' : '0%';
  if (fills[1]) fills[1].style.width = filled2 ? '100%' : (hasLoc ? '100%' : '0%');
}

function showFieldMsg(id, msg, ok) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.className = 'reg-field-msg' + (ok ? ' valid' : '');
  const input = el.closest('.reg-field')?.querySelector('input');
  if (input) {
    input.classList.remove('error', 'valid');
    if (msg && !ok) input.classList.add('error');
    else if (ok) input.classList.add('valid');
  }
}

function validateRegField(id, checkFn) {
  const input = document.getElementById(id);
  if (!input) return false;
  const result = checkFn(input.value);
  showFieldMsg(id + 'Msg', result.msg, result.ok);
  return result.ok;
}

function validateAllRegFields() {
  const fields = [
    { id: 'regName', check: v => ({ ok: v.trim().length >= 2, msg: v.trim().length < 2 ? 'Agency name is required' : '' }) },
    { id: 'regRegion', check: v => ({ ok: v.trim().length >= 2, msg: v.trim().length < 2 ? 'Region is required' : '' }) },
    { id: 'regPhone', check: v => ({ ok: /^\+?[\d\s\-()]{7,}$/.test(v.trim()), msg: /^\+?[\d\s\-()]{7,}$/.test(v.trim()) ? '' : 'Enter a valid phone number' }) },
    { id: 'regEmail', check: v => ({ ok: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()), msg: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()) ? '' : 'Enter a valid email address' }) },
  ];
  let allOk = true;
  fields.forEach(f => { if (!validateRegField(f.id, f.check)) allOk = false; });
  return allOk;
}

// ── Password strength ──

function ratePassword(pw) {
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[a-z]/.test(pw) && /[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^a-zA-Z0-9]/.test(pw)) score++;
  return score;
}

function updatePasswordStrength() {
  const pw = document.getElementById('regPassword').value;
  const confirm = document.getElementById('regConfirm').value;
  const fill = document.getElementById('regPwFill');
  const text = document.getElementById('regPwText');
  if (!fill || !text) return;
  if (!pw) {
    fill.style.width = '0';
    fill.style.background = '';
    text.textContent = '';
    showFieldMsg('regPwMsg', '', false);
    return;
  }
  const score = ratePassword(pw);
  const pct = (score / 5) * 100;
  fill.style.width = pct + '%';
  let label, color;
  if (score <= 1) { label = 'Weak'; color = 'var(--critical)'; }
  else if (score <= 2) { label = 'Fair'; color = 'var(--high)'; }
  else if (score <= 3) { label = 'Good'; color = 'var(--medium)'; }
  else if (score <= 4) { label = 'Strong'; color = 'var(--low)'; }
  else { label = 'Very Strong'; color = 'var(--accent)'; }
  fill.style.background = color;
  text.textContent = label;
  text.style.color = color;
  if (pw.length < 8) {
    showFieldMsg('regPwMsg', 'Minimum 8 characters', false);
  } else {
    showFieldMsg('regPwMsg', '', false);
  }
  if (confirm) {
    const match = pw === confirm;
    showFieldMsg('regConfirmMsg', match ? 'Passwords match' : 'Passwords do not match', match);
  }
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
    localStorage.setItem('besafe_agency_token',  data.token);
    localStorage.setItem('besafe_agency_profile', JSON.stringify(data.agency));

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

// ── Real-time validation ──
['regName','regRegion','regPhone','regEmail'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => {
    updateRegSteps();
    if (id === 'regName') validateRegField(id, v => ({ ok: v.trim().length >= 2, msg: v.trim().length < 2 ? 'Agency name is required' : '' }));
    if (id === 'regRegion') validateRegField(id, v => ({ ok: v.trim().length >= 2, msg: v.trim().length < 2 ? 'Region is required' : '' }));
    if (id === 'regPhone') validateRegField(id, v => ({ ok: /^\+?[\d\s\-()]{7,}$/.test(v.trim()), msg: /^\+?[\d\s\-()]{7,}$/.test(v.trim()) ? '' : 'Invalid phone number' }));
    if (id === 'regEmail') validateRegField(id, v => ({ ok: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()), msg: /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()) ? '' : 'Invalid email' }));
  });
});
document.getElementById('regPassword').addEventListener('input', () => { updatePasswordStrength(); updateRegSteps(); });
document.getElementById('regConfirm').addEventListener('input', () => { updatePasswordStrength(); updateRegSteps(); });

document.getElementById('btnRegister').addEventListener('click', async () => {
  hideError('registerError');

  const valid = validateAllRegFields();
  const password = document.getElementById('regPassword').value;
  const confirm  = document.getElementById('regConfirm').value;
  const regLat   = parseFloat(document.getElementById('regLat').value);
  const regLng   = parseFloat(document.getElementById('regLng').value);

  if (!valid) { showError('registerError', 'Please fix the highlighted fields.'); return; }
  if (password.length < 8) { showError('registerError', 'Password must be at least 8 characters.'); return; }
  if (password !== confirm) { showError('registerError', 'Passwords do not match.'); return; }
  if (isNaN(regLat) || isNaN(regLng)) { showError('registerError', 'Please set your headquarters location on the map.'); return; }

  setLoading('btnRegister', true);

  const body = {
    name: document.getElementById('regName').value.trim(),
    region: document.getElementById('regRegion').value.trim(),
    phone_number: document.getElementById('regPhone').value.trim(),
    email: document.getElementById('regEmail').value.trim(),
    password,
    location: { lat: regLat, lng: regLng }
  };

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
    document.getElementById('loginEmail').value = body.email;
    const loginErr = document.getElementById('loginError');
    loginErr.style.color = 'var(--low)';
    loginErr.textContent = '✓ Agency registered! Sign in to continue.';
    loginErr.classList.add('visible');
    setTimeout(() => { loginErr.style.color = ''; }, 3000);

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
  const token = localStorage.getItem('besafe_agency_token');
  if (!token) return;

  try {
    const res = await fetch(`${BASE_URL}/auth/me`, {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (res.ok) {
      window.location.href = '/dashboard';
    } else {
      localStorage.removeItem('besafe_agency_token');
      localStorage.removeItem('besafe_agency_profile');
    }
  } catch (_) { /* server offline — stay on login */ }
})();
const params = new URLSearchParams(window.location.search);
if (params.get('register') === 'true') {
  window.showRegister();
}
