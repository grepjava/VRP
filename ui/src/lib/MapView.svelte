<script>
  import { onMount, onDestroy, createEventDispatcher } from 'svelte'

  export let technicians = []
  export let workOrders = []
  export let result = null
  export let ROUTE_COLORS = []
  export let pickingLocation = false
  export let dropReturnTrip = false

  const dispatch = createEventDispatcher()

  let mapEl
  let map, L
  let techMarkers = [], orderMarkers = [], routeLayers = [], routeLabels = []
  let ready = false

  const PRIORITY_COLORS = {
    emergency: '#ff2d55', critical: '#ff6b35',
    high: '#ffd60a', medium: '#0a84ff', low: '#30d158'
  }

  // Escape user-supplied strings before inserting them into Leaflet popup HTML.
  // Without this, a customer name like <script>... would execute in the browser.
  const esc = s => String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')

  onMount(async () => {
    L = (await import('leaflet')).default
    map = L.map(mapEl, { zoomControl: true }).setView([3.1200, 101.6100], 13)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap'
    }).addTo(map)
    map.on('click', e => {
      dispatch('mapClick', { lat: e.latlng.lat, lng: e.latlng.lng })
    })
    ready = true
    updateMarkers()
  })

  onDestroy(() => { if (map) map.remove() })

  function techIcon(color) {
    return L.divIcon({
      html: `<div style="
        width:32px;height:32px;border-radius:50% 50% 50% 0;
        background:${color};border:3px solid #fff;
        transform:rotate(-45deg);box-shadow:0 2px 8px rgba(0,0,0,.5)
      "></div>`,
      iconSize: [32, 32], iconAnchor: [16, 32], className: ''
    })
  }

  function orderIcon(priority, label) {
    const bg = PRIORITY_COLORS[priority] || '#0a84ff'
    return L.divIcon({
      html: `<div style="
        width:26px;height:26px;border-radius:6px;
        background:${bg};border:2px solid #fff;
        box-shadow:0 2px 6px rgba(0,0,0,.5);
        display:flex;align-items:center;justify-content:center;
        font-size:11px;font-weight:700;color:#000
      ">${label}</div>`,
      iconSize: [26, 26], iconAnchor: [13, 13], className: ''
    })
  }

  function clearAll() {
    ;[...techMarkers, ...orderMarkers, ...routeLayers, ...routeLabels].forEach(l => l.remove())
    techMarkers = []; orderMarkers = []; routeLayers = []; routeLabels = []
  }

  function updateMarkers() {
    if (!ready) return
    clearAll()

    technicians.forEach((tech, i) => {
      const color = ROUTE_COLORS[i % ROUTE_COLORS.length]
      const m = L.marker([tech.start_location.latitude, tech.start_location.longitude], { icon: techIcon(color) })
        .bindPopup(`<b>🔧 ${esc(tech.name)}</b><br>${esc(tech.start_location.address)}<br>Skills: ${esc(tech.skills.join(', '))}`)
        .addTo(map)
      techMarkers.push(m)
    })

    workOrders.forEach((order, i) => {
      const label = String(i + 1)
      const m = L.marker([order.location.latitude, order.location.longitude], { icon: orderIcon(order.priority, label) })
        .bindPopup(`<b>${esc(order.customer_name || order.id)}</b><br>${esc(order.location.address)}<br>
          <span style="color:${PRIORITY_COLORS[order.priority] || '#0a84ff'}">${esc(order.priority)}</span> · ${esc(order.work_type)}<br>
          ⏱ ${Number(order.service_time)} min`)
        .addTo(map)
      orderMarkers.push(m)
    })

    if (result?.routes) drawRoutes()
  }

  async function drawRoutes() {
    for (const [i, route] of result.routes.entries()) {
      if (!route.assignments?.length) continue
      const tech = technicians.find(t => t.id === route.technician_id)
      if (!tech) continue
      const techIdx = technicians.findIndex(t => t.id === route.technician_id)
      const color = ROUTE_COLORS[(techIdx >= 0 ? techIdx : i) % ROUTE_COLORS.length]

      const sorted = route.assignments
        .filter(a => !a.work_order_id?.startsWith('break'))
        .sort((a, b) => a.sequence_order - b.sequence_order)

      const pts = [
        [tech.start_location.longitude, tech.start_location.latitude],
        ...sorted.map(a => {
          const o = workOrders.find(o => o.id === a.work_order_id)
          return o ? [o.location.longitude, o.location.latitude] : null
        }).filter(Boolean),
        ...(dropReturnTrip ? [] : [[tech.start_location.longitude, tech.start_location.latitude]])
      ]

      if (pts.length < 2) continue

      // Number markers on the route
      sorted.forEach((a, idx) => {
        const o = workOrders.find(o => o.id === a.work_order_id)
        if (!o) return
        const badge = L.divIcon({
          html: `<div style="background:${color};color:#fff;border-radius:50%;width:18px;height:18px;
            font-size:10px;font-weight:700;display:flex;align-items:center;justify-content:center;
            border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.5)">${idx + 1}</div>`,
          iconSize: [18, 18], iconAnchor: [9, 9], className: ''
        })
        routeLabels.push(L.marker([o.location.latitude, o.location.longitude], { icon: badge, zIndexOffset: 1000 }).addTo(map))
      })

      try {
        const coord = pts.map(([ln, lt]) => `${ln},${lt}`).join(';')
        const res = await fetch(`/osrm/route/v1/driving/${coord}?overview=full&geometries=geojson`)
        const data = await res.json()
        if (data.routes?.[0]?.geometry) {
          const layer = L.geoJSON(data.routes[0].geometry, {
            style: { color, weight: 5, opacity: 0.85 }
          }).addTo(map)
          routeLayers.push(layer)
        }
      } catch {
        const latlngs = pts.map(([ln, lt]) => [lt, ln])
        routeLayers.push(L.polyline(latlngs, { color, weight: 5, opacity: 0.85, dashArray: '8,4' }).addTo(map))
      }
    }
  }

  $: if (ready) { technicians; workOrders; result; updateMarkers() }
  $: if (map) map.getContainer().style.cursor = pickingLocation ? 'crosshair' : ''
</script>

<div style="position:relative;width:100%;height:100%">
  <div bind:this={mapEl} style="width:100%;height:100%"></div>
  <div class="map-legend">
    <div class="legend-title">Priority</div>
    {#each [['emergency','#ff2d55'],['critical','#ff6b35'],['high','#ffd60a'],['medium','#0a84ff'],['low','#30d158']] as [label, color]}
      <div class="legend-row">
        <span class="legend-swatch" style="background:{color}"></span>
        <span class="legend-label">{label}</span>
      </div>
    {/each}
  </div>
</div>

<style>
  .map-legend {
    position: absolute;
    bottom: 28px;
    right: 10px;
    background: rgba(20, 22, 40, 0.88);
    border: 1px solid #2d3250;
    border-radius: 8px;
    padding: 8px 10px;
    z-index: 1000;
    display: flex;
    flex-direction: column;
    gap: 5px;
    pointer-events: none;
    backdrop-filter: blur(4px);
  }
  .legend-title {
    font-size: 10px;
    font-weight: 700;
    color: #8892b0;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 2px;
  }
  .legend-row {
    display: flex;
    align-items: center;
    gap: 7px;
  }
  .legend-swatch {
    width: 14px;
    height: 14px;
    border-radius: 4px;
    border: 1.5px solid rgba(255,255,255,0.25);
    flex-shrink: 0;
  }
  .legend-label {
    font-size: 11px;
    color: #c8d0e0;
    text-transform: capitalize;
  }
</style>
