let regMap = null;
let regMarker = null;

function initRegMap() {
  if (regMap) return;  // ← already initialized, don't run twice

  regMap = L.map('regMap', {
    center: [15.5007, 32.5599],
    zoom: 6,
    zoomControl: true,
    attributionControl: false
  });

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19
  }).addTo(regMap);

  regMap.on('click', function (e) {
    const lat = e.latlng.lat.toFixed(6);
    const lng = e.latlng.lng.toFixed(6);
    document.getElementById('regLat').value = lat;
    document.getElementById('regLng').value = lng;
    if (regMarker) {
      regMarker.setLatLng(e.latlng);
    } else {
      regMarker = L.marker(e.latlng).addTo(regMap);
    }
  });

  document.getElementById('regLat').addEventListener('input', syncRegMarker);
  document.getElementById('regLng').addEventListener('input', syncRegMarker);
}

function syncRegMarker() {
  const lat = parseFloat(document.getElementById('regLat').value);
  const lng = parseFloat(document.getElementById('regLng').value);
  if (isNaN(lat) || isNaN(lng) || !regMap) return;
  const ll = L.latLng(lat, lng);
  if (regMarker) {
    regMarker.setLatLng(ll);
  } else {
    regMarker = L.marker(ll).addTo(regMap);
  }
  regMap.setView(ll, 10);
}