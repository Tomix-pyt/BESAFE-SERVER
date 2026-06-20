const BASE_URL = 'http://localhost:5000';
const PAGE_SIZE = 10;

const MAPBOX_TOKEN = window.MAPBOX_TOKEN;
const MAPBOX_STYLES = {
  dark: 'mapbox://styles/mapbox/dark-v11',
  satellite: 'mapbox://styles/mapbox/satellite-streets-v12',
  streets: 'mapbox://styles/mapbox/streets-v12',
};

let token, agency, socket, map;
let alerts = {}, reports = {};
let currentPage = 'overview';
let alertFilter = 'all', reportFilter = 'all';
let alertSearch = '', reportSearch = '';
let alertTimeFilter = 'all', reportTimeFilter = 'all';
let alertPage = 1, reportPage = 1;
let selectedType = null, selectedId = null;
let isTracking = false, trackPoints = [];
let settingsLocMap = null, settingsLocMarker = null;
let notifs = [];
let reRankTimer, statsTimer;

function authHeaders() {
  return { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
}

function logout() {
  localStorage.removeItem('sentinelx_token');
  localStorage.removeItem('sentinelx_agency');
  window.location.href = '/';
}

function escHtml(s = '') {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function timeAgo(iso) {
  if (!iso) return '';
  const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
  if (diff < 60) return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff/60)}m`;
  if (diff < 86400) return `${Math.floor(diff/3600)}h`;
  return `${Math.floor(diff/86400)}d`;
}

function timeFilterCutoff(filter) {
  if (filter === 'today') return Date.now() - 86400000;
  if (filter === '7d') return Date.now() - 7 * 86400000;
  if (filter === '30d') return Date.now() - 30 * 86400000;
  return 0;
}

function calcPriority(alert) {
  const conf = parseFloat(alert.confidence || 0);
  const created = new Date(alert.created_at);
  const mins = (Date.now() - created) / 60000;
  const timeW = Math.min(mins / 30, 1.0);
  const unacked = alert.status === 'active' ? 1.0 : 0.0;
  return parseFloat((conf * 0.6 + timeW * 0.3 + unacked * 0.1).toFixed(4));
}

function priorityLabel(score) {
  if (score >= 0.75) return 'CRITICAL';
  if (score >= 0.50) return 'HIGH';
  if (score >= 0.25) return 'MEDIUM';
  return 'LOW';
}

function priorityColor(label) {
  return { CRITICAL: '#f91919', HIGH: '#ff6b00', MEDIUM: '#f0b429', LOW: '#17c983' }[label] || '#f91919';
}

function reportCategoryLabel(cat) {
  return { 'abuse-home': 'Abuse at home', harassment: 'Harassment', 'unsafe-ride': 'Unsafe ride', threats: 'Threats', other: 'Other' }[cat] || cat;
}

function reportCategoryIcon(cat) {
  return { 'abuse-home': '🏠', harassment: '👁', 'unsafe-ride': '🚗', threats: '⚠', other: '📄' }[cat] || '📋';
}

function reportCategoryColor(cat) {
  return { 'abuse-home': '#e74c3c', harassment: '#f39c12', 'unsafe-ride': '#9b59b6', threats: '#c0392b', other: '#7f8c8d' }[cat] || '#7f8c8d';
}

function reportPriorityColor(p) {
  return { urgent: '#f91919', high: '#ff6b00', medium: '#f0b429', low: '#17c983' }[p] || '#7f8c8d';
}

function statusColor(status) {
  const map = {
    active: '#f91919', pending_analysis: '#353fab', triaged: '#3d7fff',
    acknowledged: '#f0b429', resolved: '#17c983', closed: '#5a7ba0',
    pending: '#353fab', completed: '#17c983', new: '#353fab',
    reviewing: '#f0b429'
  };
  return map[status] || '#5a7ba0';
}

// ═══════════════════════════════════════════════════════════
//  NAVIGATION
// ═══════════════════════════════════════════════════════════

function navigateTo(page) {
  currentPage = page;
  closeDetailPanel();
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  const target = document.getElementById(`page${page.charAt(0).toUpperCase() + page.slice(1)}`);
  if (target) target.classList.add('active');
  const navBtn = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (navBtn) navBtn.classList.add('active');

  if (page === 'overview') renderOverview();
  else if (page === 'alerts') { alertPage = 1; renderAlertList(); }
  else if (page === 'reports') { reportPage = 1; renderReportList(); }
  else if (page === 'map') { initMapFull(); refreshMapMarkers(); setTimeout(() => map && map.resize(), 100); }
  else if (page === 'settings') openSettingsPage();
}

// ═══════════════════════════════════════════════════════════
//  OVERVIEW
// ═══════════════════════════════════════════════════════════

function renderOverview() {
  try {
    const alertList = Object.values(alerts);
    const reportList = Object.values(reports);
    const activeAlerts = alertList.filter(a => a.status === 'active').length;
    const pendingReports = reportList.filter(r => r.status === 'pending_analysis').length;
    const resolvedToday = alertList.filter(a => {
      if (a.status !== 'resolved' || !a.created_at) return false;
      return Date.now() - new Date(a.created_at) < 86400000;
    }).length;

    const elActive = document.getElementById('ovActiveAlerts');
    const elPending = document.getElementById('ovPendingReports');
    const elResolved = document.getElementById('ovResolvedToday');
    const elTotal = document.getElementById('ovTotalAll');
    if (elActive) elActive.textContent = activeAlerts;
    if (elPending) elPending.textContent = pendingReports;
    if (elResolved) elResolved.textContent = resolvedToday;
    if (elTotal) elTotal.textContent = alertList.length + reportList.length;

    const skelAlert = document.getElementById('ovAlertSkel');
    const skelReport = document.getElementById('ovReportSkel');
    if (skelAlert) skelAlert.style.display = 'none';
    if (skelReport) skelReport.style.display = 'none';

    const recentAlerts = alertList.sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 7);
    const recentReports = reportList.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)).slice(0, 7);

    const alertContainer = document.getElementById('ovAlertList');
    if (alertContainer) {
      alertContainer.innerHTML = recentAlerts.length
        ? recentAlerts.map(a => renderMiniAlertCard(a)).join('')
        : '<div class="empty-state" style="display:flex"><div class="empty-icon">📭</div><p>No recent alerts</p></div>';
    }

    const reportContainer = document.getElementById('ovReportList');
    if (reportContainer) {
      reportContainer.innerHTML = recentReports.length
        ? recentReports.map(r => renderMiniReportCard(r)).join('')
        : '<div class="empty-state" style="display:flex"><div class="empty-icon">📭</div><p>No recent reports</p></div>';
    }
  } catch(e) {
    console.error('renderOverview error:', e);
  }
}

function renderMiniAlertCard(a) {
  const pLabel = priorityLabel(calcPriority(a));
  const color = priorityColor(pLabel);
  return `<div class="mini-card" onclick="openAlertDetail('${a.id}')">
    <div class="mini-left" style="border-left-color:${color}">
      <div class="mini-name">${escHtml(a.user_name)}</div>
      <div class="mini-text">${escHtml(a.transcribed_text).slice(0, 50)}${a.transcribed_text && a.transcribed_text.length > 50 ? '…' : ''}</div>
    </div>
    <div class="mini-right">
      <span class="tag" style="color:${statusColor(a.status)};border-color:${statusColor(a.status)}">${a.status}</span>
      <span class="mini-time">${timeAgo(a.created_at)}</span>
    </div>
  </div>`;
}

function renderMiniReportCard(r) {
  const color = reportCategoryColor(r.category);
  return `<div class="mini-card" onclick="openReportDetail('${r.id}')">
    <div class="mini-left">
      <span class="mini-icon" style="background:${color}20">${reportCategoryIcon(r.category)}</span>
      <div>
        <div class="mini-name">${reportCategoryLabel(r.category)}</div>
        <div class="mini-text">${escHtml(r.description).slice(0, 50)}${r.description && r.description.length > 50 ? '…' : ''}</div>
      </div>
    </div>
    <div class="mini-right">
      <span class="tag" style="color:${statusColor(r.status)};border-color:${statusColor(r.status)}">${r.status === 'pending_analysis' ? 'Pending' : r.status}</span>
      <span class="mini-time">${timeAgo(r.createdAt)}</span>
    </div>
  </div>`;
}

// ═══════════════════════════════════════════════════════════
//  ALERTS
// ═══════════════════════════════════════════════════════════

function setAlertFilter(filter) {
  alertFilter = filter;
  alertPage = 1;
  document.querySelectorAll('#pageAlerts .filter-tabs button').forEach(b => b.classList.toggle('active', b.dataset.filter === filter));
  renderAlertList();
}

function onAlertSearch() {
  alertSearch = document.getElementById('alertSearch').value.toLowerCase();
  alertPage = 1;
  renderAlertList();
}

function onAlertFilterChange() {
  alertTimeFilter = document.getElementById('alertTimeFilter').value;
  alertPage = 1;
  renderAlertList();
}

function getFilteredAlerts() {
  let list = Object.values(alerts);
  if (alertFilter !== 'all') list = list.filter(a => a.status === alertFilter);
  if (alertSearch) list = list.filter(a => (a.user_name || '').toLowerCase().includes(alertSearch) || (a.transcribed_text || '').toLowerCase().includes(alertSearch));
  const cutoff = timeFilterCutoff(alertTimeFilter);
  if (cutoff) list = list.filter(a => new Date(a.created_at).getTime() >= cutoff);
  return list.map(a => ({ ...a, priority: calcPriority(a) })).sort((a, b) => b.priority - a.priority);
}

function renderAlertList() {
  const all = getFilteredAlerts();
  const totalPages = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
  if (alertPage > totalPages) alertPage = totalPages;
  const pageItems = all.slice((alertPage - 1) * PAGE_SIZE, alertPage * PAGE_SIZE);

  const container = document.getElementById('alertListContainer');
  const empty = document.getElementById('alertEmptyState');
  const pagination = document.getElementById('alertPagination');

  document.getElementById('alertBadge').textContent = Object.values(alerts).filter(a => a.status === 'active').length;

  if (all.length === 0) {
    container.innerHTML = '';
    empty.style.display = 'flex';
    pagination.innerHTML = '';
    return;
  }
  empty.style.display = 'none';

  container.innerHTML = pageItems.map(a => {
    const pLabel = priorityLabel(a.priority);
    const color = priorityColor(pLabel);
    const confPct = Math.round(parseFloat(a.confidence || 0) * 100);
    const isAnalyzed = a.ai_analysis && a.analysis_status === 'completed';
    const isNew = (Date.now() - new Date(a.created_at)) < 30000;

    return `<div class="list-card ${isNew ? 'new-item' : ''}" data-id="${a.id}" onclick="openAlertDetail('${a.id}')">
      <div class="card-stripe" style="background:${color}"></div>
      <div class="card-body">
        <div class="card-head">
          <span class="card-title">${escHtml(a.user_name)}</span>
          <span class="card-time">${timeAgo(a.created_at)}</span>
        </div>
        <div class="card-sub">${escHtml(a.transcribed_text).slice(0, 120)}${a.transcribed_text && a.transcribed_text.length > 120 ? '…' : ''}</div>
        <div class="card-foot">
          <span class="tag" style="color:${statusColor(a.status)};border-color:${statusColor(a.status)}">${a.status.toUpperCase()}</span>
          <span class="tag" style="color:${color};border-color:${color}">${pLabel}</span>
          <span class="card-conf">${confPct}%</span>
          <div class="card-actions">
            ${!isAnalyzed ? `<button class="btn-sm btn-analyze" onclick="event.stopPropagation();analyzeAlert('${a.id}')">🔍 Analyze</button>` : `<span class="tag" style="color:var(--low);border-color:var(--low)">Analyzed ✓</span>`}
          </div>
        </div>
      </div>
    </div>`;
  }).join('');

  pagination.innerHTML = renderPagination(alertPage, totalPages, (p) => { alertPage = p; renderAlertList(); });
}

// ═══════════════════════════════════════════════════════════
//  REPORTS
// ═══════════════════════════════════════════════════════════

function setReportFilter(filter) {
  reportFilter = filter;
  reportPage = 1;
  document.querySelectorAll('#pageReports .filter-tabs button').forEach(b => b.classList.toggle('active', b.dataset.filter === filter));
  renderReportList();
}

function onReportSearch() {
  reportSearch = document.getElementById('reportSearch').value.toLowerCase();
  reportPage = 1;
  renderReportList();
}

function onReportFilterChange() {
  reportTimeFilter = document.getElementById('reportTimeFilter').value;
  reportPage = 1;
  renderReportList();
}

function getFilteredReports() {
  let list = Object.values(reports);
  if (reportFilter !== 'all') list = list.filter(r => r.status === reportFilter);
  if (reportSearch) list = list.filter(r => (r.description || '').toLowerCase().includes(reportSearch));
  const cutoff = timeFilterCutoff(reportTimeFilter);
  if (cutoff) list = list.filter(r => new Date(r.createdAt).getTime() >= cutoff);
  return list.sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

function renderReportList() {
  const all = getFilteredReports();
  const totalPages = Math.max(1, Math.ceil(all.length / PAGE_SIZE));
  if (reportPage > totalPages) reportPage = totalPages;
  const pageItems = all.slice((reportPage - 1) * PAGE_SIZE, reportPage * PAGE_SIZE);

  const container = document.getElementById('reportListContainer');
  const empty = document.getElementById('reportEmptyState');
  const pagination = document.getElementById('reportPagination');

  document.getElementById('reportBadge').textContent = Object.values(reports).filter(r => r.status === 'pending_analysis').length;

  if (all.length === 0) {
    container.innerHTML = '';
    empty.style.display = 'flex';
    pagination.innerHTML = '';
    return;
  }
  empty.style.display = 'none';

  container.innerHTML = pageItems.map(r => {
    const color = reportCategoryColor(r.category);
    const pColor = reportPriorityColor(r.priority);
    const isAnalyzed = r.ai_Analysis && r.status !== 'pending_analysis';

    return `<div class="list-card" data-id="${r.id}" onclick="openReportDetail('${r.id}')">
      <div class="card-stripe" style="background:${color}"></div>
      <div class="card-body">
        <div class="card-head">
          <span class="card-icon" style="background:${color}20">${reportCategoryIcon(r.category)}</span>
          <span class="card-title">${reportCategoryLabel(r.category)}</span>
          <span class="card-time">${timeAgo(r.createdAt)}</span>
        </div>
        <div class="card-sub">${escHtml(r.description).slice(0, 120)}${r.description && r.description.length > 120 ? '…' : ''}</div>
        <div class="card-foot">
          <span class="tag" style="color:${statusColor(r.status)};border-color:${statusColor(r.status)}">${r.status === 'pending_analysis' ? 'PENDING' : r.status.toUpperCase()}</span>
          <span class="tag" style="color:${pColor};border-color:${pColor}">${r.priority.toUpperCase()}</span>
          <div class="card-actions">
            ${!isAnalyzed ? `<button class="btn-sm btn-analyze" onclick="event.stopPropagation();analyzeReport('${r.id}')">🔍 Analyze</button>` : `<span class="tag" style="color:var(--low);border-color:var(--low)">Analyzed ✓</span>`}
          </div>
        </div>
      </div>
    </div>`;
  }).join('');

  pagination.innerHTML = renderPagination(reportPage, totalPages, (p) => { reportPage = p; renderReportList(); });
}

// ═══════════════════════════════════════════════════════════
//  PAGINATION
// ═══════════════════════════════════════════════════════════

function renderPagination(current, total, onClick) {
  if (total <= 1) return '';
  let html = '<div class="pagination-inner">';
  html += `<button class="page-btn" ${current <= 1 ? 'disabled' : ''} onclick="onPageClick(${current - 1}, ${onClick})">‹</button>`;
  for (let i = 1; i <= total; i++) {
    if (i === current || (i >= current - 1 && i <= current + 1) || i === 1 || i === total) {
      html += `<button class="page-btn ${i === current ? 'active' : ''}" onclick="onPageClick(${i}, ${onClick})">${i}</button>`;
    } else if (i === current - 2 || i === current + 2) {
      html += `<span class="page-dots">…</span>`;
    }
  }
  html += `<button class="page-btn" ${current >= total ? 'disabled' : ''} onclick="onPageClick(${current + 1}, ${onClick})">›</button>`;
  html += '</div>';
  return html;
}

function onPageClick(page, fn) {
  fn(page);
}

// ═══════════════════════════════════════════════════════════
//  DETAIL PANEL (reusable for both alerts & reports)
// ═══════════════════════════════════════════════════════════

function openDetailPanel(type, id) {
  selectedType = type;
  selectedId = id;
  const overlay = document.getElementById('detailOverlay');
  const panel = document.getElementById('detailPanel');
  const body = document.getElementById('detailBody');
  const typeEl = document.getElementById('detailType');

  overlay.style.display = 'block';
  panel.classList.add('open');
  typeEl.textContent = type === 'alert' ? 'Alert Detail' : 'Report Detail';

  body.innerHTML = '<div class="skeleton-card"><div class="sk-line"></div><div class="sk-line"></div><div class="sk-line short"></div></div>';

  if (type === 'alert') renderAlertDetail(id);
  else renderReportDetail(id);
}

function closeDetailPanel() {
  selectedType = null;
  selectedId = null;
  isTracking = false;
  try {
    map && map.getSource('track-point') && map.getSource('track-point').setData({ type: 'FeatureCollection', features: [] });
    map && map.getSource('track-line') && map.getSource('track-line').setData({ type: 'FeatureCollection', features: [] });
  } catch(e) {}
  document.getElementById('detailOverlay').style.display = 'none';
  document.getElementById('detailPanel').classList.remove('open');
}

function openAlertDetail(id) {
  openDetailPanel('alert', id);
  fetch(`${BASE_URL}/alerts/${id}`, { headers: authHeaders() })
    .then(r => r.json())
    .then(data => {
      alerts[id] = { ...alerts[id], ...data };
      if (selectedId === id) renderAlertDetail(id);
    }).catch(() => {});
}

function renderAlertDetail(id) {
  const a = alerts[id];
  if (!a) return;
  const pLabel = priorityLabel(calcPriority(a));
  const color = priorityColor(pLabel);
  const confPct = Math.round(parseFloat(a.confidence || 0) * 100);
  const isAnalyzed = a.ai_analysis && a.analysis_status === 'completed';

  let xaiHtml = '';
  if (isAnalyzed && a.ai_analysis) {
    const ai = a.ai_analysis;
    xaiHtml = `<div class="xai-panel">
      <div class="xai-header">AI Threat Analysis</div>
      <div class="xai-grid">
        <div class="xai-cell">
          <span class="xai-label">Severity</span>
          <div class="xai-meter"><div class="xai-fill" style="width:${(ai.severity_rating || 0) * 100}%;background:${priorityColor(priorityLabel(ai.severity_rating || 0))}"></div></div>
          <span class="xai-val">${((ai.severity_rating || 0) * 100).toFixed(0)}%</span>
        </div>
        <div class="xai-cell"><span class="xai-label">Pattern</span><span class="xai-val">${ai.identified_pattern_type || '—'}</span></div>
        <div class="xai-cell"><span class="xai-label">Escalation</span><span class="xai-val" style="color:${ai.escalation_risk === 'HIGH' ? 'var(--critical)' : ai.escalation_risk === 'MEDIUM' ? 'var(--medium)' : 'var(--low)'}">${ai.escalation_risk || '—'}</span></div>
        <div class="xai-cell"><span class="xai-label">Urgency</span><span class="xai-val" style="color:${ai.timeline_urgency === 'IMMEDIATE' ? 'var(--critical)' : 'var(--medium)'}">${ai.timeline_urgency || '—'}</span></div>
        <div class="xai-cell"><span class="xai-label">Isolation Risk</span><span class="xai-val" style="color:${ai.isolation_risk_detected ? 'var(--critical)' : 'var(--low)'}">${ai.isolation_risk_detected ? '⚠ Detected' : 'None'}</span></div>
        <div class="xai-cell"><span class="xai-label">Investigation</span><span class="xai-val" style="color:${priorityColor(ai.investigative_priority || 'LOW')}">${ai.investigative_priority || '—'}</span></div>
      </div>
      ${ai.pattern_tags && ai.pattern_tags.length ? `<div class="xai-tags">${ai.pattern_tags.map(t => `<span class="tag" style="color:var(--accent);border-color:var(--accent)">${t}</span>`).join('')}</div>` : ''}
      ${ai.explainable_ai_report ? `<div class="xai-report">${escHtml(ai.explainable_ai_report)}</div>` : ''}
    </div>`;
  }

  const body = document.getElementById('detailBody');
  body.innerHTML = `
    <div class="detail-section">
      <div class="detail-avatar">${a.user_photo ? `<img src="${a.user_photo}" alt="">` : (a.user_name ? a.user_name[0].toUpperCase() : '?')}</div>
      <div>
        <div class="detail-name">${escHtml(a.user_name)}</div>
        <div class="detail-meta">${escHtml(a.user_phone)}</div>
      </div>
    </div>
    <div class="detail-grid">
      <div class="detail-cell"><span class="cell-label">Status</span><span class="tag" style="color:${statusColor(a.status)};border-color:${statusColor(a.status)}">${a.status.toUpperCase()}</span></div>
      <div class="detail-cell"><span class="cell-label">Priority</span><span style="color:${color};font-weight:700">${pLabel}</span></div>
      <div class="detail-cell"><span class="cell-label">Confidence</span><span style="color:var(--critical);font-weight:700">${confPct}%</span></div>
      <div class="detail-cell"><span class="cell-label">Time</span>${new Date(a.created_at).toLocaleString()}</div>
      <div class="detail-cell span-2"><span class="cell-label">Location</span>${a.gps_lat ? `${parseFloat(a.gps_lat).toFixed(4)}, ${parseFloat(a.gps_lng).toFixed(4)}` : 'N/A'}</div>
    </div>
    ${a.track && a.track.length ? `<div class="detail-track-info"><span class="cell-label">GPS Track Points</span> ${a.track.length} points recorded</div>` : ''}
    <div class="detail-block">
      <div class="block-label">Transcribed Audio</div>
      <p>${escHtml(a.transcribed_text) || '—'}</p>
    </div>
    ${xaiHtml}
    <div class="detail-actions">
      ${!isAnalyzed ? `<button class="btn-action btn-analyze-full" onclick="analyzeAlert('${id}')">🔍 Analyze with AI</button>` : ''}
      <button class="btn-action btn-outline" onclick="viewOnMap('alert','${id}')">🗺 View on Map</button>
      <button class="btn-action btn-ack" ${a.status !== 'active' ? 'disabled' : ''} onclick="updateAlertStatus('${id}','acknowledged')">✓ Acknowledge</button>
      <button class="btn-action btn-resolve" ${a.status === 'resolved' ? 'disabled' : ''} onclick="updateAlertStatus('${id}','resolved')">✔ Resolve</button>
      <button class="btn-action btn-track ${isTracking ? 'tracking' : ''}" onclick="toggleTracking('${id}')">${isTracking ? '🔴 Stop Tracking' : '📍 Track Live'}</button>
    </div>
  `;
}

function openReportDetail(id) {
  openDetailPanel('report', id);
  fetch(`${BASE_URL}/agency/reports/${id}`, { headers: authHeaders() })
    .then(r => r.json())
    .then(data => {
      reports[id] = { ...reports[id], ...data };
      if (selectedId === id) renderReportDetail(id);
    }).catch(() => {});
}

function renderReportDetail(id) {
  const r = reports[id];
  if (!r) return;
  const color = reportCategoryColor(r.category);
  const pColor = reportPriorityColor(r.priority);
  const isAnalyzed = r.ai_Analysis && r.status !== 'pending_analysis';

  let xaiHtml = '';
  if (isAnalyzed && r.ai_Analysis) {
    const ai = r.ai_Analysis;
    xaiHtml = `<div class="xai-panel">
      <div class="xai-header">AI Threat Analysis</div>
      <div class="xai-grid">
        <div class="xai-cell">
          <span class="xai-label">Severity</span>
          <div class="xai-meter"><div class="xai-fill" style="width:${(ai.severity_rating || 0) * 100}%;background:${priorityColor(priorityLabel(ai.severity_rating || 0))}"></div></div>
          <span class="xai-val">${((ai.severity_rating || 0) * 100).toFixed(0)}%</span>
        </div>
        <div class="xai-cell"><span class="xai-label">Pattern</span><span class="xai-val">${ai.identified_pattern_type || '—'}</span></div>
        <div class="xai-cell"><span class="xai-label">Escalation</span><span class="xai-val" style="color:${ai.escalation_risk === 'HIGH' ? 'var(--critical)' : ai.escalation_risk === 'MEDIUM' ? 'var(--medium)' : 'var(--low)'}">${ai.escalation_risk || '—'}</span></div>
        <div class="xai-cell"><span class="xai-label">Urgency</span><span class="xai-val" style="color:${ai.timeline_urgency === 'IMMEDIATE' ? 'var(--critical)' : 'var(--medium)'}">${ai.timeline_urgency || '—'}</span></div>
        <div class="xai-cell"><span class="xai-label">Isolation Risk</span><span class="xai-val" style="color:${ai.isolation_risk_detected ? 'var(--critical)' : 'var(--low)'}">${ai.isolation_risk_detected ? '⚠ Detected' : 'None'}</span></div>
        <div class="xai-cell"><span class="xai-label">Investigation</span><span class="xai-val" style="color:${priorityColor(ai.investigative_priority || 'LOW')}">${ai.investigative_priority || '—'}</span></div>
      </div>
      ${ai.pattern_tags && ai.pattern_tags.length ? `<div class="xai-tags">${ai.pattern_tags.map(t => `<span class="tag" style="color:var(--accent);border-color:var(--accent)">${t}</span>`).join('')}</div>` : ''}
      ${ai.explainable_ai_report ? `<div class="xai-report">${escHtml(ai.explainable_ai_report)}</div>` : ''}
    </div>`;
  }

  const body = document.getElementById('detailBody');
  body.innerHTML = `
    <div class="detail-section">
      <span class="detail-icon" style="background:${color}20;color:${color};font-size:28px">${reportCategoryIcon(r.category)}</span>
      <div>
        <div class="detail-name">${reportCategoryLabel(r.category)}</div>
        <div class="detail-meta">Safe Chat Report</div>
      </div>
    </div>
    <div class="detail-grid">
      <div class="detail-cell"><span class="cell-label">Status</span><span class="tag" style="color:${statusColor(r.status)};border-color:${statusColor(r.status)}">${r.status === 'pending_analysis' ? 'PENDING' : r.status.toUpperCase()}</span></div>
      <div class="detail-cell"><span class="cell-label">Priority</span><span style="color:${pColor};font-weight:700">${r.priority.toUpperCase()}</span></div>
      <div class="detail-cell"><span class="cell-label">Timing</span>${r.timing || '—'}</div>
      <div class="detail-cell"><span class="cell-label">Frequency</span>${r.frequency || '—'}</div>
      <div class="detail-cell span-2"><span class="cell-label">Created</span>${new Date(r.createdAt).toLocaleString()}</div>
      ${r.location ? `<div class="detail-cell span-2"><span class="cell-label">Location</span>${r.location.lat ? `${r.location.lat}, ${r.location.lng}` : 'N/A'}</div>` : ''}
    </div>
    <div class="detail-block">
      <div class="block-label">Description</div>
      <p>${escHtml(r.description) || '—'}</p>
    </div>
    ${r.attachments && r.attachments.length ? `<div class="detail-block"><div class="block-label">Attachments (${r.attachments.length})</div><div class="attach-list">${r.attachments.map(a => `<a href="${a.url || a.uri}" target="_blank" class="attach-item">📎 ${escHtml(a.name)}</a>`).join('')}</div></div>` : ''}
    ${xaiHtml}
    <div class="detail-actions">
      ${!isAnalyzed ? `<button class="btn-action btn-analyze-full" onclick="analyzeReport('${id}')">🔍 Analyze with AI</button>` : ''}
      ${r.location ? `<button class="btn-action btn-outline" onclick="viewOnMap('report','${id}')">🗺 View on Map</button>` : ''}
      <button class="btn-action btn-ack" ${r.status !== 'pending_analysis' && r.status !== 'triaged' ? 'disabled' : ''} onclick="updateReportStatus('${id}','reviewing')">🔍 Review</button>
      <button class="btn-action btn-resolve" ${r.status === 'resolved' || r.status === 'closed' ? 'disabled' : ''} onclick="updateReportStatus('${id}','resolved')">✔ Resolve</button>
      <button class="btn-action btn-close-report" ${r.status === 'closed' ? 'disabled' : ''} onclick="updateReportStatus('${id}','closed')">✕ Close</button>
    </div>
  `;
}

// ═══════════════════════════════════════════════════════════
//  ANALYSIS (API calls)
// ═══════════════════════════════════════════════════════════

async function analyzeAlert(id) {
  const btn = document.querySelector(`[data-id="${id}"] .btn-analyze`) || document.querySelector('.btn-analyze-full');
  if (btn) { btn.textContent = 'Analyzing…'; btn.disabled = true; }
  try {
    const res = await fetch(`${BASE_URL}/alerts/${id}/analyze`, { method: 'POST', headers: authHeaders() });
    if (!res.ok) { const err = await res.json().catch(()=>({})); showToast('Analysis Failed', err.detail || 'Could not analyze alert'); if(btn){btn.textContent='🔍 Analyze';btn.disabled=false;} return; }
    const data = await res.json();
    if (data.success && alerts[id]) {
      alerts[id].ai_analysis = data.analysis;
      alerts[id].analysis_status = 'completed';
      if (selectedId === id && selectedType === 'alert') renderAlertDetail(id);
      renderAlertList();
      showToast('Analysis Complete', 'AI threat analysis is ready');
    }
  } catch(e) { console.error(e); showToast('Error', 'Failed to analyze alert'); if(btn){btn.textContent='🔍 Analyze';btn.disabled=false;} }
}

async function analyzeReport(id) {
  const btn = document.querySelector(`[data-id="${id}"] .btn-analyze`) || document.querySelector('.btn-analyze-full');
  if (btn) { btn.textContent = 'Analyzing…'; btn.disabled = true; }
  try {
    const res = await fetch(`${BASE_URL}/agency/reports/${id}/analyze`, { method: 'POST', headers: authHeaders() });
    if (!res.ok) { const err = await res.json().catch(()=>({})); showToast('Analysis Failed', err.detail || 'Could not analyze report'); if(btn){btn.textContent='🔍 Analyze';btn.disabled=false;} return; }
    const data = await res.json();
    if (data.success && reports[id]) {
      reports[id].ai_Analysis = data.analysis;
      reports[id].status = 'triaged';
      if (selectedId === id && selectedType === 'report') renderReportDetail(id);
      renderReportList();
      showToast('Analysis Complete', 'AI threat analysis is ready');
    }
  } catch(e) { console.error(e); showToast('Error', 'Failed to analyze report'); if(btn){btn.textContent='🔍 Analyze';btn.disabled=false;} }
}

// ═══════════════════════════════════════════════════════════
//  STATUS UPDATES
// ═══════════════════════════════════════════════════════════

async function updateAlertStatus(id, status) {
  try {
    const res = await fetch(`${BASE_URL}/alerts/${id}/status`, { method: 'PATCH', headers: authHeaders(), body: JSON.stringify({ status }) });
    if (res.ok) {
      alerts[id].status = status;
      if (selectedId === id && selectedType === 'alert') renderAlertDetail(id);
      renderAlertList();
      renderOverview();
      showToast('Status Updated', `Alert marked as ${status}`);
    }
  } catch(e) { console.error(e); }
}

async function updateReportStatus(id, status) {
  try {
    const res = await fetch(`${BASE_URL}/agency/reports/${id}/status`, { method: 'PATCH', headers: authHeaders(), body: JSON.stringify({ status }) });
    if (res.ok) {
      reports[id].status = status;
      if (selectedId === id && selectedType === 'report') renderReportDetail(id);
      renderReportList();
      renderOverview();
      showToast('Status Updated', `Report marked as ${status}`);
    }
  } catch(e) { console.error(e); }
}

// ═══════════════════════════════════════════════════════════
//  MAP (Mapbox GL)
// ═══════════════════════════════════════════════════════════

function initMapFull() {
  if (map) { map.resize(); return; }
  map = new mapboxgl.Map({
    container: 'mapFull',
    style: MAPBOX_STYLES.dark,
    accessToken: MAPBOX_TOKEN,
    center: [8.6753, 9.0820],
    zoom: 6,
    attributionControl: false
  });
  map.addControl(new mapboxgl.NavigationControl(), 'top-right');

  map.on('load', () => {
    addAlertReportSources();
    refreshMapMarkers();
  });

  map.on('click', 'alerts-point', (e) => {
    const p = e.features[0].properties;
    new mapboxgl.Popup({ offset: 10, className: 'map-popup' })
      .setLngLat(e.features[0].geometry.coordinates)
      .setHTML(`<strong style="color:${p.color}">${escHtml(p.name)}</strong><br>${Math.round(parseFloat(p.confidence||0)*100)}% · ${timeAgo(p.time)}<br><a href="#" onclick="openAlertDetail('${p.id}');return false;">View Detail →</a>`)
      .addTo(map);
  });
  map.on('mouseenter', 'alerts-point', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'alerts-point', () => { map.getCanvas().style.cursor = ''; });

  map.on('click', 'reports-point', (e) => {
    const p = e.features[0].properties;
    new mapboxgl.Popup({ offset: 10, className: 'map-popup' })
      .setLngLat(e.features[0].geometry.coordinates)
      .setHTML(`<strong style="color:${p.color}">${escHtml(p.label)}</strong><br>${p.priority.toUpperCase()} priority · ${timeAgo(p.time)}<br><a href="#" onclick="openReportDetail('${p.id}');return false;">View Detail →</a>`)
      .addTo(map);
  });
  map.on('mouseenter', 'reports-point', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'reports-point', () => { map.getCanvas().style.cursor = ''; });
}

function addClusterSource(sourceId, color) {
  map.addSource(sourceId, {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] },
    cluster: true,
    clusterMaxZoom: 14,
    clusterRadius: 50
  });

  map.addLayer({
    id: sourceId + '-cluster',
    type: 'circle',
    source: sourceId,
    filter: ['has', 'point_count'],
    paint: {
      'circle-color': color,
      'circle-radius': ['step', ['get', 'point_count'], 20, 10, 30, 50, 40],
      'circle-opacity': 0.85,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff'
    }
  });

  map.addLayer({
    id: sourceId + '-cluster-count',
    type: 'symbol',
    source: sourceId,
    filter: ['has', 'point_count'],
    layout: {
      'text-field': ['get', 'point_count_abbreviated'],
      'text-font': ['DIN Pro Medium', 'Arial Unicode MS Bold'],
      'text-size': 12
    },
    paint: {
      'text-color': '#ffffff'
    }
  });

  map.addLayer({
    id: sourceId + '-point',
    type: 'circle',
    source: sourceId,
    filter: ['!', ['has', 'point_count']],
    paint: {
      'circle-color': color,
      'circle-radius': sourceId === 'alerts' ? 7 : 5,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
      'circle-opacity': 0.9
    }
  });

  map.on('click', sourceId + '-cluster', (e) => {
    const features = map.queryRenderedFeatures(e.point, { layers: [sourceId + '-cluster'] });
    const clusterId = features[0].properties.cluster_id;
    map.getSource(sourceId).getClusterExpansionZoom(clusterId, (err, zoom) => {
      if (err) return;
      map.flyTo({ center: features[0].geometry.coordinates, zoom });
    });
  });
  map.on('mouseenter', sourceId + '-cluster', () => { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', sourceId + '-cluster', () => { map.getCanvas().style.cursor = ''; });
}

function addAlertReportSources() {
  addClusterSource('alerts', '#ff4444');
  addClusterSource('reports', '#ffbb00');

  // Tracking sources
  map.addSource('track-point', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] }
  });
  map.addLayer({
    id: 'track-point-layer',
    type: 'circle',
    source: 'track-point',
    paint: {
      'circle-color': '#353fab',
      'circle-radius': 8,
      'circle-stroke-width': 2,
      'circle-stroke-color': '#ffffff',
      'circle-opacity': 0.9
    }
  });

  map.addSource('track-line', {
    type: 'geojson',
    data: { type: 'FeatureCollection', features: [] }
  });
  map.addLayer({
    id: 'track-line-layer',
    type: 'line',
    source: 'track-line',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: {
      'line-color': '#353fab',
      'line-width': 2,
      'line-opacity': 0.7,
      'line-dasharray': [4, 4]
    }
  });
}

function refreshMapMarkers() {
  if (!map || !map.isStyleLoaded()) return;
  const showAlerts = document.getElementById('showAlertMarkers').checked;
  const showReports = document.getElementById('showReportMarkers').checked;

  const alertFeatures = showAlerts
    ? Object.values(alerts).filter(a => a.gps_lat && a.gps_lng).map(a => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [parseFloat(a.gps_lng), parseFloat(a.gps_lat)] },
        properties: {
          id: a.id, name: a.user_name, confidence: a.confidence, time: a.created_at,
          color: priorityColor(priorityLabel(calcPriority(a))), type: 'alert'
        }
      }))
    : [];

  const reportFeatures = showReports
    ? Object.values(reports).filter(r => r.location && r.location.lat && r.location.lng).map(r => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [parseFloat(r.location.lng), parseFloat(r.location.lat)] },
        properties: {
          id: r.id, label: reportCategoryLabel(r.category), priority: r.priority, time: r.createdAt,
          color: reportCategoryColor(r.category), type: 'report'
        }
      }))
    : [];

  try {
    map.getSource('alerts').setData({ type: 'FeatureCollection', features: alertFeatures });
    map.getSource('reports').setData({ type: 'FeatureCollection', features: reportFeatures });
  } catch(e) {}
}

function viewOnMap(type, id) {
  navigateTo('map');
  setTimeout(() => {
    const showAllBtn = document.getElementById('mapShowAllBtn');

    // Find the item
    let item, feature;
    if (type === 'alert') {
      item = alerts[id];
      if (item && item.gps_lat && item.gps_lng) {
        feature = { type: 'Feature', geometry: { type: 'Point', coordinates: [parseFloat(item.gps_lng), parseFloat(item.gps_lat)] } };
      }
    } else {
      item = reports[id];
      const loc = item && item.location;
      if (loc && loc.lat && loc.lng) {
        feature = { type: 'Feature', geometry: { type: 'Point', coordinates: [parseFloat(loc.lng), parseFloat(loc.lat)] } };
      }
    }

    if (feature && map && map.isStyleLoaded()) {
      // Hide clusters, filter points to only this item
      map.setLayoutProperty('alerts-cluster', 'visibility', 'none');
      map.setLayoutProperty('reports-cluster', 'visibility', 'none');
      map.setFilter('alerts-point', ['==', ['get', 'id'], id]);
      map.setFilter('reports-point', ['==', ['get', 'id'], id]);

      map.flyTo({ center: feature.geometry.coordinates, zoom: 14 });

      // Show popup
      const color = type === 'alert'
        ? priorityColor(priorityLabel(calcPriority(item)))
        : reportCategoryColor(item.category);
      const label = type === 'alert' ? escHtml(item.user_name) : reportCategoryLabel(item.category);
      new mapboxgl.Popup({ offset: 10, className: 'map-popup' })
        .setLngLat(feature.geometry.coordinates)
        .setHTML(`<strong style="color:${color}">${label}</strong><br>Selected ${type}<br><a href="#" onclick="open${type.charAt(0).toUpperCase()+type.slice(1)}Detail('${id}');return false;">Open Detail →</a>`)
        .addTo(map);
    }

    showAllBtn.style.display = 'block';
  }, 200);
}

function showAllMapMarkers() {
  if (!map || !map.isStyleLoaded()) return;
  map.setFilter('alerts-point', null);
  map.setFilter('reports-point', null);
  map.setLayoutProperty('alerts-cluster', 'visibility', 'visible');
  map.setLayoutProperty('reports-cluster', 'visibility', 'visible');
  document.getElementById('showAlertMarkers').checked = true;
  document.getElementById('showReportMarkers').checked = true;
  document.getElementById('mapShowAllBtn').style.display = 'none';
  // Close any open popup
  if (map._popups) map._popups.forEach(p => p.remove());
  refreshMapMarkers();
}

function switchMapStyle(styleKey) {
  if (!map) return;
  const style = MAPBOX_STYLES[styleKey];
  if (!style) return;
  map.setStyle(style);
  map.once('style.load', () => {
    addAlertReportSources();
    refreshMapMarkers();
    document.querySelectorAll('.style-btn').forEach(b => b.classList.remove('active'));
    document.querySelector(`.style-btn[data-style="${styleKey}"]`).classList.add('active');
  });
}

// ═══════════════════════════════════════════════════════════
//  LIVE TRACKING
// ═══════════════════════════════════════════════════════════

function toggleTracking(id) {
  if (isTracking) { stopTracking(); }
  else { startTracking(id); }
}

function startTracking(id) {
  isTracking = true;
  trackPoints = [];
  document.getElementById('trackingBadge').style.display = 'block';
  showToast('Live Tracking', 'Now tracking victim location');
}

function stopTracking() {
  isTracking = false;
  trackPoints = [];
  try {
    map.getSource('track-point').setData({ type: 'FeatureCollection', features: [] });
    map.getSource('track-line').setData({ type: 'FeatureCollection', features: [] });
  } catch(e) {}
  document.getElementById('trackingBadge').style.display = 'none';
}

function handleLocationUpdate(data) {
  const alert = alerts[data.alert_id];
  if (alert) {
    alert.gps_lat = data.lat;
    alert.gps_lng = data.lng;
  }
  if (isTracking && selectedId === data.alert_id && map && map.isStyleLoaded()) {
    trackPoints.push([data.lng, data.lat]);
    try {
      map.getSource('track-point').setData({
        type: 'FeatureCollection',
        features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [data.lng, data.lat] } }]
      });
      map.getSource('track-line').setData({
        type: 'FeatureCollection',
        features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: trackPoints } }]
      });
      map.flyTo({ center: [data.lng, data.lat], zoom: map.getZoom(), duration: 500 });
    } catch(e) {}
  }
}

// ═══════════════════════════════════════════════════════════
//  WEBSOCKET
// ═══════════════════════════════════════════════════════════

function connectSocket() {
  socket = io(BASE_URL, { transports: ['websocket', 'polling'] });
  socket.on('connect', () => {
    console.log('[WS] Connected');
    socket.emit('join', { agency_id: agency.id });
  });
  socket.on('new_alert', (alert) => {
    alerts[alert.id] = alert;
    renderOverview();
    renderAlertList();
    if (currentPage === 'map') refreshMapMarkers();
    addNotif(`🔔 New Alert — ${alert.user_name}`, `${Math.round(parseFloat(alert.confidence)*100)}% confidence`);
    showToast(`🔔 New Alert — ${alert.user_name}`, `${Math.round(parseFloat(alert.confidence)*100)}% confidence · ${(alert.transcribed_text||'').slice(0,60)}…`, 6000);
    playAlertSound();
  });
  socket.on('alert_analyzed', (data) => {
    if (alerts[data.alert_id]) {
      alerts[data.alert_id].ai_analysis = data.ai_analysis;
      alerts[data.alert_id].analysis_status = 'completed';
      if (selectedId === data.alert_id && selectedType === 'alert') renderAlertDetail(data.alert_id);
      renderAlertList();
      showToast('Analysis Ready', 'Alert has been analyzed by AI');
    }
  });
  socket.on('location_update', handleLocationUpdate);
  socket.on('alert_status_update', (data) => {
    if (alerts[data.alert_id]) {
      alerts[data.alert_id].status = data.status;
      if (selectedId === data.alert_id && selectedType === 'alert') renderAlertDetail(data.alert_id);
      renderAlertList();
      renderOverview();
    }
  });
  socket.on('new_report', (report) => {
    reports[report.id] = report;
    renderOverview();
    renderReportList();
    if (currentPage === 'map') refreshMapMarkers();
    addNotif(`📋 New Report — ${reportCategoryLabel(report.category)}`, `${report.priority.toUpperCase()} priority`);
    showToast(`📋 New Report`, `${reportCategoryLabel(report.category)} · ${report.priority.toUpperCase()} priority`, 6000);
    playAlertSound();
  });
  socket.on('report_analyzed', (data) => {
    if (reports[data.report_id]) {
      reports[data.report_id].ai_Analysis = data.ai_Analysis;
      reports[data.report_id].status = 'triaged';
      if (selectedId === data.report_id && selectedType === 'report') renderReportDetail(data.report_id);
      renderReportList();
      showToast('Analysis Ready', 'Report has been analyzed by AI');
    }
  });
  socket.on('report_status_update', (data) => {
    if (reports[data.report_id]) {
      reports[data.report_id].status = data.status;
      if (selectedId === data.report_id && selectedType === 'report') renderReportDetail(data.report_id);
      renderReportList();
      renderOverview();
    }
  });
  socket.on('disconnect', () => console.log('[WS] Disconnected'));
}

// ═══════════════════════════════════════════════════════════
//  DATA FETCHING
// ═══════════════════════════════════════════════════════════

async function fetchWithTimeout(url, opts, ms = 10000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    const res = await fetch(url, { ...opts, signal: ctrl.signal });
    return res;
  } finally {
    clearTimeout(timer);
  }
}

function hideSkeletons() {
  document.querySelectorAll('.skeleton-card').forEach(el => el.style.display = 'none');
}

async function fetchAlerts() {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/alerts?status=all`, { headers: authHeaders() });
    if (!res.ok) { if (res.status === 401) logout(); hideSkeletons(); return; }
    const list = await res.json();
    list.forEach(a => { alerts[a.id] = a; });
    renderAlertList();
    renderOverview();
  } catch(e) {
    console.error('Fetch alerts failed:', e);
    hideSkeletons();
    document.getElementById('alertListContainer').innerHTML = '<div class="empty-state" style="display:flex"><div class="empty-icon">⚠</div><p>Failed to load alerts. Check connection.</p></div>';
    document.getElementById('alertEmptyState').style.display = 'none';
  }
}

async function fetchReports() {
  try {
    const res = await fetchWithTimeout(`${BASE_URL}/agency/reports?status=all`, { headers: authHeaders() });
    if (!res.ok) { if (res.status === 401) logout(); hideSkeletons(); return; }
    const list = await res.json();
    list.forEach(r => { reports[r.id] = r; });
    renderReportList();
    renderOverview();
  } catch(e) {
    console.error('Fetch reports failed:', e);
    hideSkeletons();
    document.getElementById('reportListContainer').innerHTML = '<div class="empty-state" style="display:flex"><div class="empty-icon">⚠</div><p>Failed to load reports. Check connection.</p></div>';
    document.getElementById('reportEmptyState').style.display = 'none';
  }
}

// ═══════════════════════════════════════════════════════════
//  AGENCY DROPDOWN
// ═══════════════════════════════════════════════════════════

function toggleAgencyMenu() {
  const menu = document.getElementById('agencyMenu');
  menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
}
document.addEventListener('click', (e) => {
  const dd = document.getElementById('agencyDropdown');
  if (dd && !dd.contains(e.target)) {
    document.getElementById('agencyMenu').style.display = 'none';
  }
});

// ═══════════════════════════════════════════════════════════
//  NOTIFICATIONS
// ═══════════════════════════════════════════════════════════

function addNotif(title, body) {
  notifs.unshift({ title, body, time: Date.now() });
  if (notifs.length > 50) notifs.pop();
  const dot = document.getElementById('notifDot');
  dot.style.display = 'block';
  renderNotifs();
}

function toggleNotifPanel() {
  const panel = document.getElementById('notifPanel');
  panel.style.display = panel.style.display === 'none' || panel.style.display === '' ? 'block' : 'none';
  document.getElementById('notifDot').style.display = 'none';
  renderNotifs();
}

function renderNotifs() {
  const list = document.getElementById('notifList');
  if (notifs.length === 0) {
    list.innerHTML = '<div class="notif-empty">No notifications</div>';
    return;
  }
  list.innerHTML = notifs.map(n => `<div class="notif-item"><div class="notif-title">${n.title}</div><div class="notif-body">${n.body}</div><div class="notif-time">${timeAgo(n.time)} ago</div></div>`).join('');
}

// ═══════════════════════════════════════════════════════════
//  TOAST
// ═══════════════════════════════════════════════════════════

function showToast(title, body, duration = 4000) {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerHTML = `<div class="toast-title">${title}</div><div class="toast-body">${body}</div>`;
  container.appendChild(toast);
  setTimeout(() => { toast.classList.add('fading'); setTimeout(() => toast.remove(), 400); }, duration);
}

function playAlertSound() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    [880, 660, 880].forEach((freq, i) => {
      const osc = ctx.createOscillator(), gain = ctx.createGain();
      osc.connect(gain); gain.connect(ctx.destination);
      osc.frequency.value = freq; osc.type = 'sine';
      gain.gain.setValueAtTime(0, ctx.currentTime + i * 0.15);
      gain.gain.linearRampToValueAtTime(0.3, ctx.currentTime + i * 0.15 + 0.05);
      gain.gain.linearRampToValueAtTime(0, ctx.currentTime + i * 0.15 + 0.15);
      osc.start(ctx.currentTime + i * 0.15);
      osc.stop(ctx.currentTime + i * 0.15 + 0.2);
    });
  } catch(_) {}
}

// ═══════════════════════════════════════════════════════════
//  SETTINGS
// ═══════════════════════════════════════════════════════════

function openSettingsPage() {
  document.getElementById('setName').value = agency.name || '';
  document.getElementById('setRegion').value = agency.region || '';
  document.getElementById('setPhone').value = agency.phone_number || '';
  document.getElementById('setEmail').value = agency.email || '';
  clearSettingsMsgs();
  setTimeout(initSettingsLocMap, 200);
}

function clearSettingsMsgs() {
  ['settingsMsg','pwMsg','locMsg'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.textContent = ''; el.style.display = 'none'; el.className = 'settings-msg'; }
  });
}

function showSettingsMsg(id, msg, isError = true) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
  el.className = `settings-msg ${isError ? 'error' : 'success'}`;
  if (!isError) setTimeout(() => { el.style.display = 'none'; }, 4000);
}

async function saveDetails() {
  const name = document.getElementById('setName').value.trim();
  const region = document.getElementById('setRegion').value.trim();
  const phone = document.getElementById('setPhone').value.trim();
  const email = document.getElementById('setEmail').value.trim();
  if (!name || !region || !phone || !email) { showSettingsMsg('settingsMsg', 'All fields are required.'); return; }
  try {
    const res = await fetch(`${BASE_URL}/agency/update`, { method: 'PATCH', headers: authHeaders(), body: JSON.stringify({ name, region, phone_number: phone, email }) });
    const data = await res.json();
    if (!res.ok) { showSettingsMsg('settingsMsg', data.error || 'Update failed.'); return; }
    showSettingsMsg('settingsMsg', '✓ Details updated', false);
  } catch(e) { showSettingsMsg('settingsMsg', 'Cannot reach server.'); }
}

async function savePassword() {
  const currentPw = document.getElementById('setCurrentPw').value;
  const newPw = document.getElementById('setNewPw').value;
  const confirmPw = document.getElementById('setConfirmPw').value;
  if (!currentPw || !newPw || !confirmPw) { showSettingsMsg('pwMsg', 'All password fields are required.'); return; }
  if (newPw.length < 8) { showSettingsMsg('pwMsg', 'Password must be at least 8 characters.'); return; }
  if (newPw !== confirmPw) { showSettingsMsg('pwMsg', 'Passwords do not match.'); return; }
  try {
    const res = await fetch(`${BASE_URL}/agency/password`, { method: 'PATCH', headers: authHeaders(), body: JSON.stringify({ current_password: currentPw, new_password: newPw }) });
    const data = await res.json();
    if (!res.ok) { showSettingsMsg('pwMsg', data.error || 'Update failed.'); return; }
    document.getElementById('setCurrentPw').value = '';
    document.getElementById('setNewPw').value = '';
    document.getElementById('setConfirmPw').value = '';
    showSettingsMsg('pwMsg', '✓ Password updated', false);
  } catch(e) { showSettingsMsg('pwMsg', 'Cannot reach server.'); }
}

function initSettingsLocMap() {
  const container = document.getElementById('settingsLocationMap');
  if (!container) return;
  if (settingsLocMap) { settingsLocMap.resize(); return; }
  settingsLocMap = new mapboxgl.Map({
    container: 'settingsLocationMap',
    style: MAPBOX_STYLES.dark,
    accessToken: MAPBOX_TOKEN,
    center: [8.6753, 9.0820],
    zoom: 6,
    attributionControl: false,
    interactive: true
  });

  settingsLocMarker = new mapboxgl.Marker({ draggable: true, color: '#353fab' })
    .setLngLat([8.6753, 9.0820])
    .addTo(settingsLocMap);

  settingsLocMap.on('click', (e) => {
    settingsLocMarker.setLngLat(e.lngLat);
    document.getElementById('setLocLat').value = e.lngLat.lat.toFixed(6);
    document.getElementById('setLocLng').value = e.lngLat.lng.toFixed(6);
  });

  settingsLocMarker.on('dragend', () => {
    const lngLat = settingsLocMarker.getLngLat();
    document.getElementById('setLocLat').value = lngLat.lat.toFixed(6);
    document.getElementById('setLocLng').value = lngLat.lng.toFixed(6);
  });

  document.getElementById('setLocLat').addEventListener('input', syncSettingsLocMarker);
  document.getElementById('setLocLng').addEventListener('input', syncSettingsLocMarker);

  setTimeout(() => {
    const loc = agency.location;
    if (loc && loc.coordinates) {
      document.getElementById('setLocLat').value = loc.coordinates[0];
      document.getElementById('setLocLng').value = loc.coordinates[1];
      syncSettingsLocMarker();
      settingsLocMap.flyTo({ center: [loc.coordinates[1], loc.coordinates[0]], zoom: 10 });
    }
  }, 300);
}

function syncSettingsLocMarker() {
  const lat = parseFloat(document.getElementById('setLocLat').value);
  const lng = parseFloat(document.getElementById('setLocLng').value);
  if (isNaN(lat) || isNaN(lng) || !settingsLocMap) return;
  settingsLocMarker.setLngLat([lng, lat]);
  settingsLocMap.flyTo({ center: [lng, lat], zoom: settingsLocMap.getZoom(), duration: 300 });
}

async function saveLocation() {
  const lat = parseFloat(document.getElementById('setLocLat').value);
  const lng = parseFloat(document.getElementById('setLocLng').value);
  if (isNaN(lat) || isNaN(lng)) { showSettingsMsg('locMsg', 'Please select a location on the map.'); return; }
  try {
    const res = await fetch(`${BASE_URL}/agency/location`, { method: 'PATCH', headers: authHeaders(), body: JSON.stringify({ lat, lng }) });
    const data = await res.json();
    if (!res.ok) { showSettingsMsg('locMsg', data.error || 'Failed to save.'); return; }
    agency.location = { lat, lng };
    localStorage.setItem('sentinelx_agency', JSON.stringify(agency));
    showSettingsMsg('locMsg', '✓ Location saved', false);
  } catch(e) { showSettingsMsg('locMsg', 'Cannot reach server.'); }
}

// ═══════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════

async function init() {
  token = localStorage.getItem('sentinelx_token');
  agency = JSON.parse(localStorage.getItem('sentinelx_agency') || 'null');
  if (!token || !agency) { window.location.href = '/login'; return; }
  try {
    const res = await fetch(`${BASE_URL}/auth/me`, { headers: authHeaders() });
    if (!res.ok) { logout(); return; }
    const fresh = await res.json();
    agency = fresh;
    localStorage.setItem('sentinelx_agency', JSON.stringify(fresh));
  } catch(_) {}

  const avatar = document.getElementById('navAvatar');
  avatar.textContent = (agency.name || 'S')[0].toUpperCase();
  document.getElementById('navName').textContent = agency.name;
  document.getElementById('navRegion').textContent = agency.region;

  const loading = document.getElementById('loadingScreen');
  const dashboard = document.getElementById('dashboard');
  loading.classList.add('hidden');
  setTimeout(() => { loading.style.display = 'none'; }, 400);
  dashboard.style.display = 'flex';

  navigateTo('overview');
  connectSocket();
  await fetchAlerts();
  await fetchReports();
  renderOverview();

  reRankTimer = setInterval(() => {
    if (currentPage === 'alerts' || currentPage === 'overview') renderAlertList();
  }, 60000);

  statsTimer = setInterval(() => { renderOverview(); }, 30000);
}

init();