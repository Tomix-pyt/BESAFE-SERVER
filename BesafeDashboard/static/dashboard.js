// ─────────────────────────────────────────────────────────────
//  CONFIGURATIONS
// ─────────────────────────────────────────────────────────────
const BASE_URL = 'http://localhost:5000';

// ─────────────────────────────────────────────────────────────
//  STATE
// ─────────────────────────────────────────────────────────────
let token        = null;
let agency       = null;
let alerts       = {};          // Where alert.id is the key
let selectedId   = null;
let currentFilter= 'active';
let isTracking   = false;
let trackMarker  = null;
let trackLine    = null;
let trackPoints  = [];
let markers      = {};          // alert id → Leaflet marker
let map          = null;
let socket       = null;
let reRankTimer  = null;

// ─────────────────────────────────────────────────────────────
//  AUTH GUARD
// ─────────────────────────────────────────────────────────────
function authHeaders() {
  return { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' };
}

function logout() {
  localStorage.removeItem('besafe_token');
  localStorage.removeItem('besafe_agency');
  window.location.href = '/';
}

// ─────────────────────────────────────────────────────────────
//  CLOCK
// ─────────────────────────────────────────────────────────────
function startClock() {
  function tick() {
    const now = new Date();
    document.getElementById('navTime').textContent =
      now.toUTCString().slice(17, 25) + ' UTC';
  }
  tick();
  setInterval(tick, 1000);
}

// ─────────────────────────────────────────────────────────────
//  PRIORITY / COLOUR HELPERS
// ─────────────────────────────────────────────────────────────
function calcPriority(alert) {
  const conf     = parseFloat(alert.confidence || 0);
  const created  = new Date(alert.created_at);
  const mins     = (Date.now() - created) / 60000;
  const timeW    = Math.min(mins / 30, 1.0);
  const unacked  = alert.status === 'active' ? 1.0 : 0.0;
  return parseFloat((conf * 0.6 + timeW * 0.3 + unacked * 0.1).toFixed(4));
}

function priorityLabel(score) {
  if (score >= 0.75) return 'CRITICAL';
  if (score >= 0.50) return 'HIGH';
  if (score >= 0.25) return 'MEDIUM';
  return 'LOW';
}

function priorityClass(label) {
  return 'priority-' + label.toLowerCase();
}

function priorityColor(label) {
  const map = { CRITICAL: '#ff2d3a', HIGH: '#ff6b00', MEDIUM: '#f0b429', LOW: '#17c983' };
  return map[label] || '#ff2d3a';
}

function timeAgo(isoStr) {
  const diff = Math.floor((Date.now() - new Date(isoStr)) / 1000);
  if (diff < 60)  return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
  return `${Math.floor(diff/3600)}h ago`;
}

// ─────────────────────────────────────────────────────────────
//  MAP INITIALISATION
// ─────────────────────────────────────────────────────────────
function initMap() {
  map = L.map('map', {
    center: [15.5007, 32.5599],   // Khartoum, Sudan
    zoom: 7,
    zoomControl: true,
    attributionControl: false
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap'
  }).addTo(map);
}

function makeMarkerIcon(color) {
  return L.divIcon({
    className: '',
    iconSize:  [20, 20],
    iconAnchor:[10, 10],
    html: `
      <div style="position:relative;width:20px;height:20px">
        <div style="
          position:absolute;top:50%;left:50%;
          transform:translate(-50%,-50%);
          width:30px;height:30px;
          border-radius:50%;
          border:2px solid ${color};
          animation:pulse-ring 1.5s ease-out infinite;
        "></div>
        <div style="
          position:absolute;top:50%;left:50%;
          transform:translate(-50%,-50%);
          width:15px;height:15px;
          border-radius:50%;
          background:${color};
          border:2px solid #fff;
          box-shadow:0 0 8px ${color};
        "></div>
      </div>`
  });
}

function dropMarker(alert) {
  if (!alert.gps_lat || !alert.gps_lng) return;
  if (markers[alert.id]) map.removeLayer(markers[alert.id]);

  const pLabel = priorityLabel(calcPriority(alert));
  const color  = priorityColor(pLabel);
  const icon   = makeMarkerIcon(color);

  const marker = L.marker([alert.gps_lat, alert.gps_lng], { icon })
    .addTo(map)
    .bindPopup(`
      <div style="font-family:'IBM Plex Mono',monospace;font-size:12px;color:#dce6f5;background:#0a0f1a;padding:6px,border:1px solid ">
        <strong style="color:${color}">${alert.user_name}</strong><br>
        ${(parseFloat(alert.confidence)*100).toFixed(0)}% confidence<br>
        ${timeAgo(alert.created_at)}
      </div>`, { className: 'dark-popup' })
    .on('click', () => selectAlert(alert.id));

  markers[alert.id] = marker;
}

function removeMarker(id) {
  if (markers[id]) {
    map.removeLayer(markers[id]);
    delete markers[id];
  }
}

// ─────────────────────────────────────────────────────────────
//  ALERT LIST RENDERING
// ─────────────────────────────────────────────────────────────
function getFilteredAlerts() {
  const list = Object.values(alerts);
  const filtered = currentFilter === 'all'
    ? list
    : list.filter(a => a.status === currentFilter);

  // Recalculate priorities and sort
  return filtered
    .map(a => ({ ...a, priority: calcPriority(a) }))
    .sort((a, b) => b.priority - a.priority);
}

function renderAlertList() {
  const list     = getFilteredAlerts();
  const container= document.getElementById('alertList');
  const empty    = document.getElementById('emptyState');
  const badge    = document.getElementById('alertCountBadge');

  badge.textContent = list.length;

  if (list.length === 0) {
    container.innerHTML = '';
    container.appendChild(empty);
    empty.style.display = 'flex';
    return;
  }

  empty.style.display = 'none';

  list.forEach(alert => {
    const existing  = container.querySelector(`[data-id="${alert.id}"]`);
    const pLabel    = priorityLabel(alert.priority);
    const color     = priorityColor(pLabel);
    const confPct   = Math.round(parseFloat(alert.confidence || 0) * 100);
    const isNew     = (Date.now() - new Date(alert.created_at)) < 30000;

    const html = `
      <div class="alert-card ${priorityClass(pLabel)} ${alert.id === selectedId ? 'selected' : ''} ${isNew ? 'new-alert' : ''}"
           data-id="${alert.id}"
           onclick="selectAlert('${alert.id}')">
        <div class="card-top">
          <div class="card-user">${escHtml(alert.user_name)}</div>
          <span class="tag ${pLabel.toLowerCase()}">${pLabel}</span>
        </div>
        <div class="card-meta">
          <span class="tag ${alert.status}">${alert.status.toUpperCase()}</span>
          <span class="card-time">${timeAgo(alert.created_at)}</span>
        </div>
        <div class="card-text">"${escHtml(alert.transcribed_text)}"</div>
        <div class="card-footer">
          <div class="confidence-bar">
            <div class="fill" style="width:${confPct}%;background:${color}"></div>
          </div>
          <span class="confidence-val">${confPct}%</span>
        </div>
      </div>`;

    if (existing) {
      existing.outerHTML = html;
    } else {
      container.insertAdjacentHTML('beforeend', html);
    }
  });

  // Remove cards that are no longer in the filtered list I.E this is when there is a reranking
  const ids = new Set(list.map(a => a.id));
  container.querySelectorAll('.alert-card').forEach(card => {
    if (!ids.has(card.dataset.id)) card.remove();
  });
}

// ─────────────────────────────────────────────────────────────
//  DETAIL PANEL
// ─────────────────────────────────────────────────────────────
function selectAlert(id) {
  selectedId = id;
  const alert = alerts[id];
  if (!alert) return;

  stopTracking();

  const pScore = calcPriority(alert);
  const pLabel = priorityLabel(pScore);
  const color  = priorityColor(pLabel);
  const confPct= Math.round(parseFloat(alert.confidence || 0) * 100);

  // Victim info
  const avatar = document.getElementById('victimAvatar');
  if (alert.user_photo) {
    avatar.innerHTML = `<img src="${alert.user_photo}" alt="${alert.user_name}" onerror="this.parentElement.textContent='${alert.user_name[0].toUpperCase()}'">`;
  } else {
    avatar.textContent = alert.user_name ? alert.user_name[0].toUpperCase() : '?';
  }

  document.getElementById('victimName').textContent  = alert.user_name;
  document.getElementById('victimPhone').textContent = alert.user_phone;

  // Grid which contains all the information on the user and informaion
  document.getElementById('detailStatus').innerHTML =
    `<span class="tag ${alert.status}">${alert.status.toUpperCase()}</span>`;
  document.getElementById('detailPriority').innerHTML =
    `<span style="color:${color}">${pLabel} (${pScore})</span>`;
  document.getElementById('detailTime').textContent =
    new Date(alert.created_at).toLocaleTimeString();
  document.getElementById('detailCoords').textContent =
    alert.gps_lat ? `${parseFloat(alert.gps_lat).toFixed(4)}, ${parseFloat(alert.gps_lng).toFixed(4)}` : 'N/A';

  // Confidence counter
  document.getElementById('detailConfPct').textContent = `${confPct}%`;
  document.getElementById('detailConfBar').style.width      = `${confPct}%`;
  document.getElementById('detailConfBar').style.background = color;

  // Transcripted Text
  document.getElementById('detailText').textContent = alert.transcribed_text || '—';

  // Buttons to resolve and acknowledge a case
  const btnAck = document.getElementById('btnAck');
  const btnRes = document.getElementById('btnResolve');
  btnAck.disabled = alert.status !== 'active';
  btnRes.disabled = alert.status === 'resolved';

  // Show panel + update layout i.e rerender the alerts after there is an action
  const panel = document.getElementById('detailPanel');
  panel.style.display = 'flex';
  document.getElementById('mainArea').classList.add('detail-open');

  // Re-render list to update selected state
  renderAlertList();

  // Pan map to victim (this is a default code from leaflet documentation)
  if (alert.gps_lat && alert.gps_lng) {
    map.setView([alert.gps_lat, alert.gps_lng], 13, { animate: true });
  }

  if (markers[id]) markers[id].openPopup();
}

function closeDetail() {
  stopTracking();
  selectedId = null;
  document.getElementById('detailPanel').style.display = 'none';
  document.getElementById('mainArea').classList.remove('detail-open');
  renderAlertList();
}

// ─────────────────────────────────────────────────────────────
//  STATUS UPDATES
// ─────────────────────────────────────────────────────────────
async function updateStatus(newStatus) {
  if (!selectedId) return;

  try {
    const res = await fetch(`${BASE_URL}/alerts/${selectedId}/status`, {
      method:  'PATCH',
      headers: authHeaders(),
      body:    JSON.stringify({ status: newStatus })
    });

    if (res.ok) {
      alerts[selectedId].status = newStatus;
      selectAlert(selectedId);        // refresh panel
      renderAlertList();
      fetchStats();
      showToast('Status Updated', `Alert marked as ${newStatus}.`);
    }
  } catch (err) {
    console.error('Status update failed:', err);
  }
}

// ─────────────────────────────────────────────────────────────
//  LIVE TRACKING (not fullly included due to lack of database collection and privacy issues)
// ─────────────────────────────────────────────────────────────
function toggleTracking() {
  if (isTracking) {
    stopTracking();
  } else {
    startTracking();
  }
}

function startTracking() {
  if (!selectedId) return;
  isTracking = true;
  trackPoints = [];

  const btn = document.getElementById('btnTrack');
  btn.textContent = '🔴 Stop Live Tracking';
  btn.classList.add('tracking');
  document.getElementById('trackingBadge').style.display = 'block';

  showToast('Live Tracking', 'Now tracking victim location in real-time.');
}

function stopTracking() {
  isTracking = false;
  if (trackMarker) { map.removeLayer(trackMarker); trackMarker = null; }
  if (trackLine)   { map.removeLayer(trackLine);   trackLine   = null; }
  trackPoints = [];

  const btn = document.getElementById('btnTrack');
  if (btn) {
    btn.textContent = '📍 Track Live Location';
    btn.classList.remove('tracking');
  }
  document.getElementById('trackingBadge').style.display = 'none';
}

function handleLocationUpdate(data) {
  // Always update the static marker
  const alert = alerts[data.alert_id];
  if (alert) {
    alert.gps_lat = data.lat;
    alert.gps_lng = data.lng;
    if (markers[data.alert_id]) {
      markers[data.alert_id].setLatLng([data.lat, data.lng]);
    }
  }

  // If this is the alert we're actively tracking, draw the trail
  if (isTracking && selectedId === data.alert_id) {
    trackPoints.push([data.lat, data.lng]);

    if (trackMarker) {
      trackMarker.setLatLng([data.lat, data.lng]);
    } else {
      const icon = makeMarkerIcon('#3d7fff');
      trackMarker = L.marker([data.lat, data.lng], { icon }).addTo(map);
    }

    if (trackLine) {
      trackLine.setLatLngs(trackPoints);
    } else {
      trackLine = L.polyline(trackPoints, {
        color:  '#3d7fff',
        weight: 2,
        opacity:0.7,
        dashArray: '4 4'
      }).addTo(map);
    }

    map.panTo([data.lat, data.lng], { animate: true });

    // Update coords in detail panel
    document.getElementById('detailCoords').textContent =
      `${parseFloat(data.lat).toFixed(4)}, ${parseFloat(data.lng).toFixed(4)}`;
  }
}

// ─────────────────────────────────────────────────────────────
//  WEBSOCKET IMPLEMENTATION
// ─────────────────────────────────────────────────────────────
function connectSocket() {
  socket = io(BASE_URL, { transports: ['websocket', 'polling'] }); //default setup code

  socket.on('connect', () => {
    console.log('[WS] Connected');
    socket.emit('join', { agency_id: agency.id });
  });

  socket.on('new_alert', (alert) => {
    console.log('[WS] New alert:', alert);
    alerts[alert.id] = alert;
    dropMarker(alert);
    renderAlertList();
    fetchStats();
    showToast(
      ` 🔔New Alert — ${alert.user_name}`,
      `${Math.round(parseFloat(alert.confidence)*100)}% confidence · ${alert.transcribed_text.slice(0,60)}…`,
      6000
    );
    playAlertSound();
  });

  socket.on('location_update', (data) => {
    handleLocationUpdate(data);
  });

  socket.on('alert_status_update', (data) => {
    if (alerts[data.alert_id]) {
      alerts[data.alert_id].status = data.status;
      if (selectedId === data.alert_id) selectAlert(data.alert_id);
      renderAlertList();
    }
  });

  socket.on('disconnect', () => {
    console.log('[WS] Disconnected — will reconnect');
  });
}

// ─────────────────────────────────────────────────────────────
//  DATA FETCHING
// ─────────────────────────────────────────────────────────────
async function fetchAlerts(filter = currentFilter) {
  try {
    const res  = await fetch(`${BASE_URL}/alerts?status=${filter}`, {
      headers: authHeaders()
    });
    if (!res.ok) { if (res.status === 401) logout(); return; }

    const list = await res.json();
    // Merge into alerts store
    list.forEach(a => { alerts[a.id] = a; });

    // Drop markers for all fetched alerts
    list.forEach(a => dropMarker(a));

    renderAlertList();
  } catch (err) {
    console.error('Fetch alerts failed:', err);
  }
}

async function fetchStats() {
  try {
    const res  = await fetch(`${BASE_URL}/stats`, { headers: authHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('statActive').textContent   = data.active   || 0;
    document.getElementById('statAcked').textContent    = data.acknowledged || 0;
    document.getElementById('statResolved').textContent = data.resolved  || 0;
    document.getElementById('statTotal').textContent    = data.total     || 0;
  } catch (_) {}
}

// ─────────────────────────────────────────────────────────────
//  FILTER
// ─────────────────────────────────────────────────────────────
function setFilter(filter, navPill) {
  currentFilter = filter;

  // Update nav pills
  document.querySelectorAll('.stat-pill').forEach(p => p.classList.remove('filter-active'));
  if (navPill) navPill.classList.add('filter-active');

  // Update sidebar tabs
  document.querySelectorAll('.filter-tabs button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.tab === filter);
  });

  // Clear current list and re-fetch
  const list = Object.values(alerts).filter(a =>
    filter === 'all' || a.status === filter
  );
  // If we already have the data, render immediately
  if (list.length > 0 || filter === 'active') {
    renderAlertList();
  }
  // Always re-fetch to get latest
  fetchAlerts(filter);
}

// ─────────────────────────────────────────────────────────────
//  TOAST NOTIFICATIONS FOR NEW ALERT
// ─────────────────────────────────────────────────────────────
function showToast(title, body, duration = 4000) {
  const container = document.getElementById('toastContainer');
  const toast     = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<div class="toast-title">${title}</div><div class="toast-body">${body}</div>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('fading');
    setTimeout(() => toast.remove(), 400);
  }, duration);
}

// ─────────────────────────────────────────────────────────────
//  ALERT SOUND
// ─────────────────────────────────────────────────────────────
function playAlertSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [880, 660, 880].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain= ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq;
      osc.type = 'sine';
      gain.gain.setValueAtTime(0, ctx.currentTime + i * 0.15);
      gain.gain.linearRampToValueAtTime(0.3, ctx.currentTime + i * 0.15 + 0.05);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + i * 0.15 + 0.15);
      osc.start(ctx.currentTime + i * 0.15);
      osc.stop(ctx.currentTime + i * 0.15 + 0.2);
    });
  } catch (_) {}
}

// ─────────────────────────────────────────────────────────────
//  HELPERS
// ─────────────────────────────────────────────────────────────
function escHtml(str = '') {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ─────────────────────────────────────────────────────────────
//  INIIALIZATION WHEN BOOTIN THE DASHBOARD
// ─────────────────────────────────────────────────────────────
async function init() {
  token  = localStorage.getItem('besafe_token');
  agency = JSON.parse(localStorage.getItem('besafe_agency') || 'null');

  if (!token || !agency) {
    window.location.href = '/login';
    return;
  }

  // Verify token is still valid
  try {
    const res = await fetch(`${BASE_URL}/auth/me`, { headers: authHeaders() });
    if (!res.ok) { logout(); return; }
    const fresh = await res.json();
    agency = fresh;
    localStorage.setItem('besafe_agency', JSON.stringify(fresh));
  } catch (_) {
    // Server offline — continue with cached agency data
  }

  // Populate navbar
  document.getElementById('navName').textContent   = agency.name;
  document.getElementById('navRegion').textContent = agency.region;

  // Show dashboard
  const loading   = document.getElementById('loadingScreen');
  const dashboard = document.getElementById('dashboard');
  loading.classList.add('hidden');
  setTimeout(() => { loading.style.display = 'none'; }, 400);
  dashboard.style.display = 'grid';

  // Boot everything
  startClock();
  initMap();
  connectSocket();
  await fetchAlerts('active');
  await fetchStats();

  // Re-rank alert list every 60 seconds (priority scores change over time)
  reRankTimer = setInterval(() => {
    renderAlertList();
    if (selectedId && alerts[selectedId]) selectAlert(selectedId);
  }, 60000);

  // Refresh stats every 30 seconds
  setInterval(fetchStats, 30000);
}

// Boot
init();


// ═══════════════════════════════════════════════════════════════
//  SETTINGS PANEL
// ═══════════════════════════════════════════════════════════════

function openSettings() {
  // Pre-fill fields from cached agency object
  document.getElementById('setName').value   = agency.name   || '';
  document.getElementById('setRegion').value = agency.region || '';
  document.getElementById('setPhone').value  = agency.phone_number || '';
  document.getElementById('setEmail').value  = agency.email  || '';

  // Clear any previous messages
  clearSettingsMsgs();

  // If detail panel is open, close it first to avoid layout clash
  if (selectedId) closeDetail();

  const panel = document.getElementById('settingsPanel');
  panel.style.display = 'flex';
  document.getElementById('mainArea').classList.add('detail-open');
}

function closeSettings() {
  document.getElementById('settingsPanel').style.display = 'none';
  document.getElementById('mainArea').classList.remove('detail-open');
  clearSettingsMsgs();
}

function clearSettingsMsgs() {
  ['settingsError','settingsSuccess','pwError','pwSuccess'].forEach(id => {
    const el = document.getElementById(id);
    el.textContent = '';
    el.style.display = 'none';
  });
}

function showSettingsMsg(id, msg) {
  const el = document.getElementById(id);
  el.textContent = msg;
  el.style.display = 'block';
  // auto-hide success after 4s
    setTimeout(() => { el.style.display = 'none'; }, 800);
}

// ── Save agency details (name, region, phone, email)
async function saveDetails() {
  const btn    = document.getElementById('btnSaveDetails');
  const name   = document.getElementById('setName').value.trim();
  const region = document.getElementById('setRegion').value.trim();
  const phone  = document.getElementById('setPhone').value.trim();
  const email  = document.getElementById('setEmail').value.trim();

  if (!name || !region || !phone || !email) {
    showSettingsMsg('settingsError', 'All fields are required.');
    return;
  
  }

  btn.disabled    = true;
  btn.textContent = 'Saving…';

  try {
    const res  = await fetch(`${BASE_URL}/agency/update`, {
      method:  'PATCH',
      headers: authHeaders(),
      body:    JSON.stringify({ name, region, phone_number: phone, email })
    });
    const data = await res.json();

    if (!res.ok) {
      showSettingsMsg('settingsError', data.error || 'Update failed.');
      return;
    }
    showSettingsMsg('settingsSuccess', '✓ Details updated successfully.');

  } catch (err) {
    showSettingsMsg('settingsError', 'Cannot reach server.');
    console.error(err);
  } finally {
    document.getElementById('setName').value=""
    document.getElementById('setRegion').value=""
    document.getElementById('setPhone').value=""
    document.getElementById('setEmail').value=""
    btn.disabled    = false;
    btn.textContent = 'Save Changes';
  }
}

// ── Save new password
async function savePassword() {
  const btn       = document.getElementById('btnSavePw');
  const currentPw = document.getElementById('setCurrentPw').value;
  const newPw     = document.getElementById('setNewPw').value;
  const confirmPw = document.getElementById('setConfirmPw').value;

  if (!currentPw || !newPw || !confirmPw) {
    showSettingsMsg('pwError', 'All password fields are required.');
    return;
  }
  if (newPw.length < 8) {
    showSettingsMsg('pwError', 'New password must be at least 8 characters.');
    return;
  }
  if (newPw !== confirmPw) {
    showSettingsMsg('pwError', 'New passwords do not match.');
    return;
  }

  btn.disabled    = true;
  btn.textContent = 'Updating…';

  try {
    const res  = await fetch(`${BASE_URL}/agency/password`, {
      method:  'PATCH',
      headers: authHeaders(),
      body:    JSON.stringify({ current_password: currentPw, new_password: newPw })
    });
    const data = await res.json();

    if (!res.ok) {
      showSettingsMsg('pwError', data.error || 'Password update failed.');
      return;
    }

    // Clear fields on success
    document.getElementById('setCurrentPw').value = '';
    document.getElementById('setNewPw').value     = '';
    document.getElementById('setConfirmPw').value = '';
    showSettingsMsg('pwSuccess', '✓ Password updated successfully.');

  } catch (err) {
    showSettingsMsg('pwError', 'Cannot reach server.');
    console.error(err);
  } finally {
    btn.disabled    = false;
    btn.textContent = 'Update Password';
  }
}