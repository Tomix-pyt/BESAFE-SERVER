const REG_MAPBOX_TOKEN = window.REG_MAPBOX_TOKEN;

let regMapGL = null;
let regMarkerGL = null;
let regGeocoderGL = null;

function openLocationModal() {
  document.getElementById('locationModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
  if (!regMapGL) initRegMapGL();
  else regMapGL.resize();
}

function closeLocationModal() {
  document.getElementById('locationModal').style.display = 'none';
  document.body.style.overflow = '';
}

function initRegMapGL() {
  regMapGL = new mapboxgl.Map({
    container: 'regMapGL',
    style: 'mapbox://styles/mapbox/dark-v11',
    accessToken: REG_MAPBOX_TOKEN,
    center: [32.5599, 15.5007],
    zoom: 6,
    attributionControl: false
  });
  regMapGL.addControl(new mapboxgl.NavigationControl(), 'top-right');

  regGeocoderGL = new MapboxGeocoder({
    accessToken: REG_MAPBOX_TOKEN,
    mapboxgl: mapboxgl,
    marker: false,
    placeholder: 'Search for an address...',
    countries: 'SD,NG,KE,ET,SS,UG'
  });
  regMapGL.addControl(regGeocoderGL, 'top-left');

  regGeocoderGL.on('result', (e) => {
    const [lng, lat] = e.result.center;
    placeRegMarker([lng, lat]);
    regMapGL.flyTo({ center: [lng, lat], zoom: 14 });
  });

  regMapGL.on('click', (e) => {
    placeRegMarker([e.lngLat.lng, e.lngLat.lat]);
  });

  regMapGL.on('load', () => {
    regMarkerGL = new mapboxgl.Marker({ draggable: true, color: '#353fab' })
      .setLngLat([32.5599, 15.5007])
      .addTo(regMapGL);
    regMarkerGL.on('dragend', () => updateRegCoords(regMarkerGL.getLngLat()));
    updateRegCoords(regMarkerGL.getLngLat());
  });
}

function placeRegMarker(lngLat) {
  if (regMarkerGL) {
    regMarkerGL.setLngLat(lngLat);
  } else {
    regMarkerGL = new mapboxgl.Marker({ draggable: true, color: '#353fab' })
      .setLngLat(lngLat)
      .addTo(regMapGL);
    regMarkerGL.on('dragend', () => updateRegCoords(regMarkerGL.getLngLat()));
  }
  updateRegCoords(lngLat);
}

function updateRegCoords(lngLat) {
  document.getElementById('selectedCoords').textContent =
    `${lngLat.lat.toFixed(6)}, ${lngLat.lng.toFixed(6)}`;

  fetch(`https://api.mapbox.com/geocoding/v5/mapbox.places/${lngLat.lng},${lngLat.lat}.json?access_token=${REG_MAPBOX_TOKEN}`)
    .then(r => r.json())
    .then(data => {
      document.getElementById('selectedAddress').textContent =
        data.features?.[0]?.place_name || 'Unknown location';
    })
    .catch(() => {
      document.getElementById('selectedAddress').textContent = 'Could not resolve address';
    });
}

function confirmLocation() {
  if (!regMarkerGL) return;
  const lngLat = regMarkerGL.getLngLat();
  const lat = lngLat.lat.toFixed(6);
  const lng = lngLat.lng.toFixed(6);
  document.getElementById('regLat').value = lat;
  document.getElementById('regLng').value = lng;

  // Update map preview card
  const placeholder = document.getElementById('regMapPlaceholder');
  const preview = document.getElementById('regMapPreview');
  if (placeholder) placeholder.style.display = 'none';
  if (preview) preview.style.display = 'flex';

  const addr = document.getElementById('regLocAddress');
  const coords = document.getElementById('regLocCoords');
  if (addr) addr.textContent = document.getElementById('selectedAddress')?.textContent || 'Location selected';
  if (coords) coords.textContent = `${lngLat.lat.toFixed(4)}, ${lngLat.lng.toFixed(4)}`;

  // Update steps indicator
  if (typeof updateRegSteps === 'function') updateRegSteps();

  // Show field success
  const msg = document.getElementById('regLocMsg');
  if (msg) { msg.textContent = 'Location set'; msg.className = 'reg-field-msg valid'; }

  closeLocationModal();
}
