<script>
  import MapView from './lib/MapView.svelte'
  import Sidebar from './lib/Sidebar.svelte'
  import ResultsPanel from './lib/ResultsPanel.svelte'
  import { optimize } from './lib/api.js'

  const ROUTE_COLORS = ['#6c63ff','#00c896','#ff6b35','#0a84ff','#ffd60a','#ff2d55','#bf5af2','#30d158']

  const DEFAULT_TECHNICIANS = [
    {
      id: 'TECH001', name: 'Ahmad Razali',
      start_location: { latitude: 3.1073, longitude: 101.6067, address: 'SS2, Petaling Jaya' },
      work_shift: { earliest: 480, latest: 1020 },
      break_window: { earliest: 720, latest: 780 }, break_duration: 60,
      skills: ['electrical', 'maintenance'],
      max_daily_orders: 8, max_travel_time: 300, hourly_rate: 65, vehicle_type: 'van', drop_return_trip: false
    },
    {
      id: 'TECH002', name: 'Siti Norzahra',
      start_location: { latitude: 3.1478, longitude: 101.6159, address: 'Damansara Utama, PJ' },
      work_shift: { earliest: 480, latest: 1020 },
      break_window: { earliest: 720, latest: 780 }, break_duration: 60,
      skills: ['plumbing', 'inspection'],
      max_daily_orders: 8, max_travel_time: 300, hourly_rate: 60, vehicle_type: 'car', drop_return_trip: false
    },
    {
      id: 'TECH003', name: 'Raj Kumar',
      start_location: { latitude: 3.0939, longitude: 101.5984, address: 'Kelana Jaya, PJ' },
      work_shift: { earliest: 480, latest: 1020 },
      break_window: { earliest: 720, latest: 780 }, break_duration: 60,
      skills: ['HVAC', 'electrical'],
      max_daily_orders: 8, max_travel_time: 300, hourly_rate: 70, vehicle_type: 'van', drop_return_trip: false
    },
    {
      id: 'TECH004', name: 'Lim Wei Liang',
      start_location: { latitude: 3.1589, longitude: 101.6059, address: 'Bandar Utama, PJ' },
      work_shift: { earliest: 480, latest: 1020 },
      break_window: { earliest: 720, latest: 780 }, break_duration: 60,
      skills: ['networking', 'maintenance'],
      max_daily_orders: 8, max_travel_time: 300, hourly_rate: 68, vehicle_type: 'car', drop_return_trip: false
    },
    {
      id: 'TECH005', name: 'Farah Hanum',
      start_location: { latitude: 3.1189, longitude: 101.5773, address: 'Ara Damansara, PJ' },
      work_shift: { earliest: 480, latest: 1020 },
      break_window: { earliest: 720, latest: 780 }, break_duration: 60,
      skills: ['inspection', 'mechanical'],
      max_daily_orders: 8, max_travel_time: 300, hourly_rate: 62, vehicle_type: 'car', drop_return_trip: false
    }
  ]

  const DEFAULT_WORK_ORDERS = [
    { id: 'WO001', customer_name: 'One Utama Shopping Centre', location: { latitude: 3.1517, longitude: 101.6150, address: 'One Utama, Bandar Utama' }, priority: 'high', work_type: 'maintenance', service_time: 90, required_skills: ['electrical'], description: 'Main panel maintenance', estimated_value: 800, time_window: null },
    { id: 'WO002', customer_name: 'SS2 Hawker Centre', location: { latitude: 3.1089, longitude: 101.6112, address: 'SS2, Petaling Jaya' }, priority: 'medium', work_type: 'repair', service_time: 60, required_skills: ['plumbing'], description: 'Pipe leak repair', estimated_value: 350, time_window: null },
    { id: 'WO003', customer_name: 'Damansara Perdana Condo', location: { latitude: 3.1423, longitude: 101.6054, address: 'Damansara Perdana, PJ' }, priority: 'critical', work_type: 'repair', service_time: 120, required_skills: ['plumbing'], description: 'Burst pipe emergency', estimated_value: 950, time_window: null },
    { id: 'WO004', customer_name: 'Tropicana Golf Club', location: { latitude: 3.1481, longitude: 101.5973, address: 'Tropicana, PJ' }, priority: 'low', work_type: 'inspection', service_time: 60, required_skills: ['inspection'], description: 'Annual HVAC inspection', estimated_value: 400, time_window: null },
    { id: 'WO005', customer_name: 'Kelana Jaya LRT Station', location: { latitude: 3.0972, longitude: 101.5954, address: 'Kelana Jaya, PJ' }, priority: 'high', work_type: 'repair', service_time: 75, required_skills: ['electrical'], description: 'Escalator electrical fault', estimated_value: 1100, time_window: null },
    { id: 'WO006', customer_name: 'Mutiara Damansara Office', location: { latitude: 3.1572, longitude: 101.5975, address: 'Mutiara Damansara, PJ' }, priority: 'medium', work_type: 'installation', service_time: 150, required_skills: ['networking'], description: 'Network rack installation', estimated_value: 1800, time_window: null },
    { id: 'WO007', customer_name: 'Kota Damansara Clinic', location: { latitude: 3.1724, longitude: 101.5804, address: 'Kota Damansara, PJ' }, priority: 'high', work_type: 'maintenance', service_time: 60, required_skills: ['HVAC'], description: 'Chiller unit servicing', estimated_value: 700, time_window: null },
    { id: 'WO008', customer_name: 'PJ Old Town Shoplot', location: { latitude: 3.1040, longitude: 101.6430, address: 'Seksyen 52, PJ Old Town' }, priority: 'low', work_type: 'inspection', service_time: 45, required_skills: ['inspection'], description: 'Fire safety inspection', estimated_value: 250, time_window: null },
    { id: 'WO009', customer_name: 'Seksyen 14 Apartment', location: { latitude: 3.1174, longitude: 101.6434, address: 'Seksyen 14, Petaling Jaya' }, priority: 'medium', work_type: 'repair', service_time: 90, required_skills: ['electrical'], description: 'Distribution board trip', estimated_value: 450, time_window: null },
    { id: 'WO010', customer_name: 'Ara Damansara Medical Centre', location: { latitude: 3.1222, longitude: 101.5801, address: 'Ara Damansara, PJ' }, priority: 'emergency', work_type: 'repair', service_time: 60, required_skills: ['mechanical'], description: 'Generator failure', estimated_value: 2500, time_window: null },
    { id: 'WO011', customer_name: 'Empire City Mall', location: { latitude: 3.1572, longitude: 101.6050, address: 'Empire City, Damansara' }, priority: 'high', work_type: 'maintenance', service_time: 120, required_skills: ['HVAC'], description: 'Cooling tower maintenance', estimated_value: 950, time_window: null },
    { id: 'WO012', customer_name: 'Sunway Pyramid Hotel', location: { latitude: 3.0695, longitude: 101.6028, address: 'Sunway, Petaling Jaya' }, priority: 'medium', work_type: 'installation', service_time: 180, required_skills: ['networking'], description: 'CCTV system upgrade', estimated_value: 3200, time_window: null },
    { id: 'WO013', customer_name: 'Seksyen 17 Factory', location: { latitude: 3.1067, longitude: 101.6395, address: 'Seksyen 17, Petaling Jaya' }, priority: 'high', work_type: 'repair', service_time: 90, required_skills: ['mechanical'], description: 'Conveyor belt breakdown', estimated_value: 1400, time_window: null },
    { id: 'WO014', customer_name: 'Damansara Kim Restaurant', location: { latitude: 3.1329, longitude: 101.6254, address: 'Damansara Kim, PJ' }, priority: 'medium', work_type: 'repair', service_time: 45, required_skills: ['plumbing'], description: 'Grease trap blockage', estimated_value: 280, time_window: null },
    { id: 'WO015', customer_name: 'USJ Heights Residence', location: { latitude: 3.0560, longitude: 101.5820, address: 'USJ, Subang Jaya' }, priority: 'low', work_type: 'maintenance', service_time: 60, required_skills: ['maintenance'], description: 'Water pump servicing', estimated_value: 320, time_window: null },
    { id: 'WO016', customer_name: 'PJ Gateway Tower', location: { latitude: 3.1044, longitude: 101.6387, address: 'PJ Gateway, Petaling Jaya' }, priority: 'critical', work_type: 'repair', service_time: 75, required_skills: ['electrical'], description: 'Lift control panel fault', estimated_value: 1600, time_window: null },
    { id: 'WO017', customer_name: 'Taman Jaya Park Office', location: { latitude: 3.1097, longitude: 101.6317, address: 'Taman Jaya, Petaling Jaya' }, priority: 'low', work_type: 'inspection', service_time: 30, required_skills: ['inspection'], description: 'Routine electrical inspection', estimated_value: 180, time_window: null },
    { id: 'WO018', customer_name: 'Kelana Mall', location: { latitude: 3.0921, longitude: 101.6039, address: 'Kelana Jaya, PJ' }, priority: 'medium', work_type: 'maintenance', service_time: 90, required_skills: ['HVAC'], description: 'AHU filter replacement', estimated_value: 550, time_window: null },
    { id: 'WO019', customer_name: 'LDP Kota Damansara Plaza', location: { latitude: 3.1651, longitude: 101.5889, address: 'Kota Damansara, Petaling Jaya' }, priority: 'high', work_type: 'installation', service_time: 120, required_skills: ['networking'], description: 'Fibre optic termination', estimated_value: 2100, time_window: null },
    { id: 'WO020', customer_name: 'SS15 Courtyard Apartments', location: { latitude: 3.0838, longitude: 101.5938, address: 'SS15, Subang Jaya' }, priority: 'medium', work_type: 'repair', service_time: 60, required_skills: ['plumbing'], description: 'Water heater replacement', estimated_value: 480, time_window: null }
  ]

  let technicians = [...DEFAULT_TECHNICIANS]
  let workOrders = [...DEFAULT_WORK_ORDERS]
  let result = null
  let loading = false
  let error = null
  let pickingLocation = false
  let pendingLocation = null
  let showSettings = false

  let settings = {
    enforce_skill_constraints: false,
    minimize_fleet: false,
    vehicle_fixed_cost: 300,
    balance_workload: false,
    max_route_hours: 7,
    drop_return_trip: false,
    time_limit_override: false,
    time_limit_seconds: 30
  }

  function buildConfig() {
    const cfg = {}
    if (settings.enforce_skill_constraints) cfg.enforce_skill_constraints = true
    if (settings.minimize_fleet) cfg.vehicle_fixed_cost = settings.vehicle_fixed_cost
    if (settings.balance_workload) cfg.max_route_hours = settings.max_route_hours
    if (settings.time_limit_override) cfg.time_limit_override = settings.time_limit_seconds
    return Object.keys(cfg).length ? cfg : null
  }

  let optimizedDropReturnTrip = false

  // Progress bar state
  let progress = 0
  let progressPhase = ''
  let progressElapsed = 0
  let _progressTimer = null

  function estimatedSolveMs() {
    // Mirror config.py time limits; add ~4 s for OSRM matrix computation
    if (settings.time_limit_override) return (settings.time_limit_seconds + 4) * 1000
    const n = workOrders.length + 1
    if (n <= 15) return 9000
    if (n <= 50) return 14000
    if (n <= 100) return 34000
    return 64000
  }

  let nextTechId = 6
  let nextOrderId = 21

  function addTechnician(tech) {
    tech.id = `TECH${String(nextTechId++).padStart(3, '0')}`
    technicians = [...technicians, tech]
  }

  function editTechnician({ id, ...data }) {
    technicians = technicians.map(t => t.id === id ? { ...t, ...data } : t)
    result = null
  }

  function addWorkOrder(order) {
    order.id = `WO${String(nextOrderId++).padStart(3, '0')}`
    workOrders = [...workOrders, order]
  }

  function editWorkOrder({ id, ...data }) {
    workOrders = workOrders.map(o => o.id === id ? { ...o, ...data } : o)
    result = null
  }

  function handleReset() {
    technicians = [...DEFAULT_TECHNICIANS]
    workOrders = [...DEFAULT_WORK_ORDERS]
    nextTechId = 6
    nextOrderId = 21
    result = null
    error = null
  }

  function handleMapClick({ detail }) {
    pendingLocation = detail
    if (!pickingLocation) {
      const order = {
        id: `WO${String(nextOrderId++).padStart(3, '0')}`,
        customer_name: 'New Order',
        location: { latitude: detail.lat, longitude: detail.lng, address: `${detail.lat.toFixed(4)}, ${detail.lng.toFixed(4)}` },
        priority: 'medium', work_type: 'maintenance', service_time: 60,
        required_skills: [], description: '', estimated_value: 0, time_window: null
      }
      workOrders = [...workOrders, order]
    }
  }

  async function handleOptimize() {
    loading = true; error = null; result = null
    progress = 0; progressElapsed = 0
    progressPhase = 'Computing travel times…'

    const estimated = estimatedSolveMs()
    const start = Date.now()
    _progressTimer = setInterval(() => {
      const elapsed = Date.now() - start
      progressElapsed = Math.floor(elapsed / 1000)
      progress = 90 * (1 - Math.exp(-3 * elapsed / estimated))
      if (elapsed > 4000) progressPhase = 'Optimizing routes…'
    }, 100)

    try {
      optimizedDropReturnTrip = settings.drop_return_trip
      const techs = technicians.map(t => ({ ...t, drop_return_trip: settings.drop_return_trip }))
      result = await optimize(techs, workOrders, buildConfig())
      clearInterval(_progressTimer)
      progress = 100
      progressPhase = 'Done!'
      setTimeout(() => { progress = 0; progressPhase = ''; progressElapsed = 0 }, 700)
    } catch(e) {
      error = e.message
      clearInterval(_progressTimer)
      progress = 0; progressPhase = ''; progressElapsed = 0
    }
    loading = false
  }
</script>

<div class="app">
  <header>
    <div class="header-left">
      <span class="logo">⚡</span>
      <h1>cuOpt Field Service</h1>
    </div>

    <div class="header-right">
      {#if pickingLocation}
        <div class="pick-hint">Click on the map to pick a location</div>
      {/if}
      <div class="counts">
        <span>🔧 {technicians.length}</span>
        <span>📋 {workOrders.length}</span>
      </div>
      <button class="settings-btn" class:active={showSettings} on:click={() => showSettings = !showSettings}>⚙ Settings</button>
      <button class="reset-btn" on:click={handleReset} title="Reset to default data">↺ Reset</button>
      <button
        class="optimize-btn"
        on:click={handleOptimize}
        disabled={loading || technicians.length === 0 || workOrders.length === 0}
      >
        {#if loading}Optimizing…{:else}⚡ Optimize{/if}
      </button>
    </div>
  </header>

  {#if loading || progress > 0}
    <div class="progress-wrap">
      <div class="progress-track">
        <div class="progress-fill" style="width: {progress}%"></div>
      </div>
      <div class="progress-meta">
        <span class="progress-phase">{progressPhase}</span>
        <span class="progress-elapsed">{progressElapsed}s</span>
      </div>
    </div>
  {/if}

  {#if error}
    <div class="error-bar">⚠ {error}</div>
  {/if}

  <div class="main">
    <Sidebar
      {technicians} {workOrders} {ROUTE_COLORS} {pickingLocation} {pendingLocation}
      on:addTechnician={e => addTechnician(e.detail)}
      on:editTechnician={e => editTechnician(e.detail)}
      on:removeTechnician={e => { technicians = technicians.filter(t => t.id !== e.detail); result = null }}
      on:addWorkOrder={e => addWorkOrder(e.detail)}
      on:editWorkOrder={e => editWorkOrder(e.detail)}
      on:removeWorkOrder={e => { workOrders = workOrders.filter(o => o.id !== e.detail); result = null }}
      on:pickingLocation={e => { pickingLocation = e.detail; if (!e.detail) pendingLocation = null }}
    />
    <div class="map-wrap">
      <MapView
        {technicians} {workOrders} {result} {ROUTE_COLORS} {pickingLocation} dropReturnTrip={optimizedDropReturnTrip}
        on:mapClick={handleMapClick}
      />
      {#if pickingLocation}
        <div class="map-overlay">📍 Click anywhere on the map to set location</div>
      {/if}
    </div>

    {#if showSettings}
      <button class="settings-backdrop" on:click={() => showSettings = false} aria-label="Close settings"></button>
      <div class="settings-drawer" role="dialog" aria-label="Solver Settings">
        <div class="drawer-header">
          <span class="drawer-title">Solver Settings</span>
          <button class="drawer-close" on:click={() => showSettings = false}>✕</button>
        </div>
        <div class="drawer-body">

          <div class="setting-group">
            <label class="toggle-row" for="chk-skills">
              <div class="toggle-info">
                <span class="setting-name">Enforce skill matching</span>
                <span class="setting-api">add_order_vehicle_match</span>
                <span class="setting-desc">Only assign orders to technicians who have the required skills. Hard constraint — may cause infeasibility if a skill is overloaded.</span>
              </div>
              <input id="chk-skills" type="checkbox" bind:checked={settings.enforce_skill_constraints} />
            </label>
          </div>

          <div class="setting-group">
            <label class="toggle-row" for="chk-fleet">
              <div class="toggle-info">
                <span class="setting-name">Minimize fleet size</span>
                <span class="setting-api">set_vehicle_fixed_costs</span>
                <span class="setting-desc">Add a fixed cost per deployed technician — solver prefers fewer vehicles when routes can be merged.</span>
              </div>
              <input id="chk-fleet" type="checkbox" bind:checked={settings.minimize_fleet} />
            </label>
            {#if settings.minimize_fleet}
              <div class="setting-sub">
                <label class="sub-label" for="inp-fixed-cost">Fixed cost per technician</label>
                <input id="inp-fixed-cost" type="number" bind:value={settings.vehicle_fixed_cost} min="50" max="5000" step="50" class="num-input" />
              </div>
            {/if}
          </div>

          <div class="setting-group">
            <label class="toggle-row" for="chk-balance">
              <div class="toggle-info">
                <span class="setting-name">Balance workload</span>
                <span class="setting-api">add_capacity_dimension</span>
                <span class="setting-desc">Cap the maximum total time (travel + service) per technician. Forces the solver to spread work rather than overload one person.</span>
              </div>
              <input id="chk-balance" type="checkbox" bind:checked={settings.balance_workload} />
            </label>
            {#if settings.balance_workload}
              <div class="setting-sub">
                <label class="sub-label" for="inp-max-hours">Max hours per technician</label>
                <input id="inp-max-hours" type="number" bind:value={settings.max_route_hours} min="1" max="12" step="0.5" class="num-input" />
              </div>
            {/if}
          </div>

          <div class="setting-group">
            <label class="toggle-row" for="chk-return">
              <div class="toggle-info">
                <span class="setting-name">Drop return to base</span>
                <span class="setting-api">set_drop_return_trips</span>
                <span class="setting-desc">Technicians end their day at their last job site instead of returning to their start location. Reduces total travel time.</span>
              </div>
              <input id="chk-return" type="checkbox" bind:checked={settings.drop_return_trip} />
            </label>
          </div>

          <div class="setting-group">
            <label class="toggle-row" for="chk-timelimit">
              <div class="toggle-info">
                <span class="setting-name">Custom solver time limit</span>
                <span class="setting-api">SolverSettings.set_time_limit</span>
                <span class="setting-desc">Override the automatic time limit. Increase for larger problems where the solver needs more time to find a good solution.</span>
              </div>
              <input id="chk-timelimit" type="checkbox" bind:checked={settings.time_limit_override} />
            </label>
            {#if settings.time_limit_override}
              <div class="setting-sub">
                <label class="sub-label" for="inp-time-limit">Time limit (seconds)</label>
                <input id="inp-time-limit" type="number" bind:value={settings.time_limit_seconds} min="5" max="300" step="5" class="num-input" />
              </div>
            {/if}
          </div>

        </div>
      </div>
    {/if}
  </div>

  <ResultsPanel {result} {technicians} {workOrders} {ROUTE_COLORS} />
</div>

<style>
  .app { display: flex; flex-direction: column; height: 100vh; }

  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 16px; background: #1a1d2e; border-bottom: 1px solid #2d3250;
    flex-shrink: 0; gap: 12px;
  }

  .header-left { display: flex; align-items: center; gap: 10px; }
  .logo { font-size: 22px; }
  h1 { font-size: 17px; font-weight: 700; color: #fff; white-space: nowrap; }

  .header-right { display: flex; align-items: center; gap: 12px; }

  .pick-hint {
    font-size: 12px; color: #6c63ff; background: rgba(108,99,255,0.1);
    padding: 5px 10px; border-radius: 6px; border: 1px solid rgba(108,99,255,0.3);
  }

  .counts { display: flex; gap: 10px; font-size: 13px; color: #8892b0; }

  .settings-btn {
    background: #232640; color: #8892b0; padding: 9px 14px;
    border-radius: 8px; font-size: 13px; font-weight: 600;
    border: 1px solid #2d3250;
  }
  .settings-btn:hover, .settings-btn.active { color: #e0e6f0; border-color: #6c63ff; background: #2a2e55; }

  .settings-backdrop {
    position: absolute; inset: 0; background: rgba(0,0,0,0.4);
    z-index: 1000; border: none; padding: 0; cursor: default;
  }

  .settings-drawer {
    position: absolute; top: 0; right: 0; bottom: 0; width: 300px;
    background: #1a1d2e; border-left: 1px solid #2d3250;
    z-index: 1001; display: flex; flex-direction: column;
    box-shadow: -4px 0 24px rgba(0,0,0,0.4);
  }

  .drawer-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px; border-bottom: 1px solid #2d3250; flex-shrink: 0;
  }
  .drawer-title { font-size: 14px; font-weight: 700; color: #e0e6f0; }
  .drawer-close {
    background: none; border: none; color: #8892b0; font-size: 16px;
    cursor: pointer; padding: 2px 6px; border-radius: 4px;
  }
  .drawer-close:hover { color: #e0e6f0; background: #2d3250; }

  .drawer-body { flex: 1; overflow-y: auto; padding: 8px 0; }

  .setting-group {
    padding: 12px 16px; border-bottom: 1px solid #2d3250;
  }
  .setting-group:last-child { border-bottom: none; }

  .toggle-row {
    display: flex; align-items: flex-start; justify-content: space-between;
    gap: 12px; cursor: pointer;
  }
  .toggle-row input[type="checkbox"] {
    margin-top: 2px; accent-color: #6c63ff;
    width: 15px; height: 15px; flex-shrink: 0; cursor: pointer;
  }
  .toggle-info { display: flex; flex-direction: column; gap: 3px; }
  .setting-name { font-size: 13px; font-weight: 600; color: #e0e6f0; }
  .setting-api { font-size: 10px; color: #6c63ff; font-family: monospace; }
  .setting-desc { font-size: 11px; color: #8892b0; line-height: 1.4; }

  .setting-sub {
    display: flex; align-items: center; justify-content: space-between;
    margin-top: 10px; padding-top: 10px; border-top: 1px solid #2d3250;
  }
  .sub-label { font-size: 12px; color: #8892b0; }
  .num-input {
    width: 70px; padding: 5px 8px; background: #232640;
    border: 1px solid #2d3250; border-radius: 6px;
    color: #e0e6f0; font-size: 13px; text-align: right;
  }
  .num-input:focus { border-color: #6c63ff; outline: none; }

  .reset-btn {
    background: #232640; color: #8892b0; padding: 9px 14px;
    border-radius: 8px; font-size: 13px; font-weight: 600;
    border: 1px solid #2d3250;
  }
  .reset-btn:hover { color: #e0e6f0; border-color: #6c63ff; }

  .optimize-btn {
    background: #6c63ff; color: #fff; padding: 9px 22px;
    border-radius: 8px; font-size: 14px; font-weight: 700;
    display: flex; align-items: center; gap: 8px;
  }
  .optimize-btn:hover:not(:disabled) { background: #5a52d5; }

  @keyframes spin { to { transform: rotate(360deg); } }

  .progress-wrap {
    flex-shrink: 0; background: #13151f;
    border-bottom: 1px solid #2d3250;
  }
  .progress-track {
    height: 3px; background: #2d3250; width: 100%;
  }
  .progress-fill {
    height: 100%; background: #6c63ff;
    transition: width 0.1s linear;
    box-shadow: 0 0 8px rgba(108,99,255,0.6);
  }
  .progress-meta {
    display: flex; justify-content: space-between; align-items: center;
    padding: 4px 16px; font-size: 11px;
  }
  .progress-phase { color: #6c63ff; }
  .progress-elapsed { color: #8892b0; font-variant-numeric: tabular-nums; }

  .error-bar {
    background: #c0392b; color: #fff; padding: 7px 16px; font-size: 13px; flex-shrink: 0;
  }

  .main { display: flex; flex: 1; overflow: hidden; position: relative; }

  .map-wrap { flex: 1; position: relative; }

  .map-overlay {
    position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%);
    background: rgba(108,99,255,0.9); color: #fff; padding: 8px 16px;
    border-radius: 8px; font-size: 13px; pointer-events: none; z-index: 1000;
  }
</style>
