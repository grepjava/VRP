<script>
  import { createEventDispatcher } from 'svelte'
  import { minsToTime, timeToMins } from './api.js'

  export let technicians = []
  export let workOrders = []
  export let ROUTE_COLORS = []
  export let pickingLocation = false
  export let pendingLocation = null

  const dispatch = createEventDispatcher()

  let tab = 'technicians'
  let showTechForm = false
  let showOrderForm = false
  let editingTechId = null
  let editingOrderId = null

  // Technician form state
  let techForm = defaultTechForm()
  function defaultTechForm() {
    return {
      name: '', address: '', latitude: '', longitude: '',
      shiftStart: '08:00', shiftEnd: '17:00',
      breakStart: '12:00', breakEnd: '13:00', breakDuration: 60,
      skills: '', maxOrders: 8, maxTravel: 300, hourlyRate: 60, vehicleType: 'van'
    }
  }

  // Work order form state
  let orderForm = defaultOrderForm()
  function defaultOrderForm() {
    return {
      customerName: '', address: '', latitude: '', longitude: '',
      priority: 'medium', workType: 'maintenance', serviceTime: 60,
      skills: '', description: '', estimatedValue: 0
    }
  }

  // When map click comes in while picking
  $: if (pendingLocation && (showOrderForm || editingOrderId)) {
    orderForm.latitude = pendingLocation.lat.toFixed(6)
    orderForm.longitude = pendingLocation.lng.toFixed(6)
    if (!orderForm.address) orderForm.address = `${pendingLocation.lat.toFixed(4)}, ${pendingLocation.lng.toFixed(4)}`
  }
  $: if (pendingLocation && (showTechForm || editingTechId)) {
    techForm.latitude = pendingLocation.lat.toFixed(6)
    techForm.longitude = pendingLocation.lng.toFixed(6)
    if (!techForm.address) techForm.address = `${pendingLocation.lat.toFixed(4)}, ${pendingLocation.lng.toFixed(4)}`
  }

  function editTech(tech) {
    if (editingTechId === tech.id) { cancelTechEdit(); return }
    editingTechId = tech.id
    editingOrderId = null
    showTechForm = false
    showOrderForm = false
    techForm = {
      name: tech.name,
      address: tech.start_location.address || '',
      latitude: String(tech.start_location.latitude),
      longitude: String(tech.start_location.longitude),
      shiftStart: minsToTime(tech.work_shift.earliest),
      shiftEnd: minsToTime(tech.work_shift.latest),
      breakStart: minsToTime(tech.break_window.earliest),
      breakEnd: minsToTime(tech.break_window.latest),
      breakDuration: tech.break_duration,
      skills: tech.skills.join(', '),
      maxOrders: tech.max_daily_orders,
      maxTravel: tech.max_travel_time,
      hourlyRate: tech.hourly_rate,
      vehicleType: tech.vehicle_type
    }
    dispatch('pickingLocation', false)
  }

  function editOrder(order) {
    if (editingOrderId === order.id) { cancelOrderEdit(); return }
    editingOrderId = order.id
    editingTechId = null
    showTechForm = false
    showOrderForm = false
    orderForm = {
      customerName: order.customer_name || '',
      address: order.location.address || '',
      latitude: String(order.location.latitude),
      longitude: String(order.location.longitude),
      priority: order.priority,
      workType: order.work_type,
      serviceTime: order.service_time,
      skills: order.required_skills.join(', '),
      description: order.description || '',
      estimatedValue: order.estimated_value || 0
    }
    dispatch('pickingLocation', false)
  }

  function cancelTechEdit() {
    editingTechId = null
    techForm = defaultTechForm()
    dispatch('pickingLocation', false)
  }

  function cancelOrderEdit() {
    editingOrderId = null
    orderForm = defaultOrderForm()
    dispatch('pickingLocation', false)
  }

  function submitTech() {
    if (!techForm.name || !techForm.latitude || !techForm.longitude) return
    const data = {
      name: techForm.name,
      start_location: {
        latitude: parseFloat(techForm.latitude),
        longitude: parseFloat(techForm.longitude),
        address: techForm.address
      },
      work_shift: { earliest: timeToMins(techForm.shiftStart), latest: timeToMins(techForm.shiftEnd) },
      break_window: { earliest: timeToMins(techForm.breakStart), latest: timeToMins(techForm.breakEnd) },
      break_duration: techForm.breakDuration,
      skills: techForm.skills.split(',').map(s => s.trim()).filter(Boolean),
      max_daily_orders: techForm.maxOrders,
      max_travel_time: techForm.maxTravel,
      hourly_rate: techForm.hourlyRate,
      vehicle_type: techForm.vehicleType,
      drop_return_trip: false
    }
    if (editingTechId) {
      dispatch('editTechnician', { id: editingTechId, ...data })
      editingTechId = null
    } else {
      dispatch('addTechnician', data)
      showTechForm = false
    }
    techForm = defaultTechForm()
    dispatch('pickingLocation', false)
  }

  function submitOrder() {
    if (!orderForm.customerName || !orderForm.latitude || !orderForm.longitude) return
    const data = {
      customer_name: orderForm.customerName,
      location: {
        latitude: parseFloat(orderForm.latitude),
        longitude: parseFloat(orderForm.longitude),
        address: orderForm.address
      },
      priority: orderForm.priority,
      work_type: orderForm.workType,
      service_time: orderForm.serviceTime,
      required_skills: orderForm.skills.split(',').map(s => s.trim()).filter(Boolean),
      description: orderForm.description,
      estimated_value: parseFloat(orderForm.estimatedValue) || 0,
      time_window: null
    }
    if (editingOrderId) {
      dispatch('editWorkOrder', { id: editingOrderId, ...data })
      editingOrderId = null
    } else {
      dispatch('addWorkOrder', data)
      showOrderForm = false
    }
    orderForm = defaultOrderForm()
    dispatch('pickingLocation', false)
  }

  function toggleOrderForm() {
    showOrderForm = !showOrderForm
    showTechForm = false
    editingTechId = null
    editingOrderId = null
    dispatch('pickingLocation', false)
  }

  function toggleTechForm() {
    showTechForm = !showTechForm
    showOrderForm = false
    editingTechId = null
    editingOrderId = null
    dispatch('pickingLocation', false)
  }

  function pickOnMap() {
    dispatch('pickingLocation', true)
  }

  const PRIORITY_COLORS = {
    emergency: '#ff2d55', critical: '#ff6b35',
    high: '#ffd60a', medium: '#0a84ff', low: '#30d158'
  }
</script>

<aside>
  <div class="tabs">
    <button class:active={tab === 'technicians'} on:click={() => tab = 'technicians'}>
      🔧 Technicians <span class="badge">{technicians.length}</span>
    </button>
    <button class:active={tab === 'orders'} on:click={() => tab = 'orders'}>
      📋 Work Orders <span class="badge">{workOrders.length}</span>
    </button>
  </div>

  <div class="panel-content">

    {#if tab === 'technicians'}
      <div class="list">
        {#each technicians as tech, i}
          <div class="item" class:editing={editingTechId === tech.id}>
            <div class="item-color" style="background:{ROUTE_COLORS[i % ROUTE_COLORS.length]}"></div>
            <div class="item-body">
              <div class="item-name">{tech.name}</div>
              <div class="item-meta">{tech.start_location.address || `${tech.start_location.latitude}, ${tech.start_location.longitude}`}</div>
              <div class="item-meta">{minsToTime(tech.work_shift.earliest)}–{minsToTime(tech.work_shift.latest)} · {tech.skills.join(', ') || 'no skills'}</div>
            </div>
            <button class="edit-btn" class:active={editingTechId === tech.id} on:click={() => editTech(tech)} title="Edit">✏</button>
            <button class="remove-btn" on:click={() => dispatch('removeTechnician', tech.id)}>✕</button>
          </div>

          {#if editingTechId === tech.id}
            <form class="form" on:submit|preventDefault={submitTech}>
              <div class="form-title">Edit Technician</div>
              <label>Name *<input bind:value={techForm.name} placeholder="John Smith" required /></label>
              <div class="row">
                <label>Latitude *<input type="number" step="any" bind:value={techForm.latitude} placeholder="3.1073" required /></label>
                <label>Longitude *<input type="number" step="any" bind:value={techForm.longitude} placeholder="101.6067" required /></label>
              </div>
              <label>
                Address
                <div class="input-row">
                  <input bind:value={techForm.address} placeholder="e.g. Petaling Jaya" />
                  <button type="button" class="pick-btn" class:active={pickingLocation} on:click={pickOnMap} title="Click on map to pick">📍</button>
                </div>
              </label>
              <div class="row">
                <label>Shift Start<input type="time" bind:value={techForm.shiftStart} /></label>
                <label>Shift End<input type="time" bind:value={techForm.shiftEnd} /></label>
              </div>
              <div class="row">
                <label>Break Start<input type="time" bind:value={techForm.breakStart} /></label>
                <label>Break End<input type="time" bind:value={techForm.breakEnd} /></label>
              </div>
              <label>Skills (comma-separated)<input bind:value={techForm.skills} placeholder="electrical, plumbing" /></label>
              <div class="row">
                <label>Max Orders<input type="number" bind:value={techForm.maxOrders} min="1" /></label>
                <label>Vehicle<select bind:value={techForm.vehicleType}>
                  <option>van</option><option>car</option><option>truck</option><option>standard</option>
                </select></label>
              </div>
              <div class="form-actions">
                <button type="button" class="cancel-btn" on:click={cancelTechEdit}>Cancel</button>
                <button type="submit" class="submit-btn">Save Changes</button>
              </div>
            </form>
          {/if}
        {/each}
        {#if technicians.length === 0}
          <div class="empty">No technicians added</div>
        {/if}
      </div>

      <button class="add-btn" on:click={toggleTechForm}>
        {showTechForm ? '✕ Cancel' : '+ Add Technician'}
      </button>

      {#if showTechForm}
        <form class="form" on:submit|preventDefault={submitTech}>
          <div class="form-title">New Technician</div>
          <label>Name *<input bind:value={techForm.name} placeholder="John Smith" required /></label>
          <div class="row">
            <label>Latitude *<input type="number" step="any" bind:value={techForm.latitude} placeholder="3.1073" required /></label>
            <label>Longitude *<input type="number" step="any" bind:value={techForm.longitude} placeholder="101.6067" required /></label>
          </div>
          <label>
            Address
            <div class="input-row">
              <input bind:value={techForm.address} placeholder="e.g. Petaling Jaya" />
              <button type="button" class="pick-btn" class:active={pickingLocation} on:click={pickOnMap} title="Click on map to pick">📍</button>
            </div>
          </label>
          <div class="row">
            <label>Shift Start<input type="time" bind:value={techForm.shiftStart} /></label>
            <label>Shift End<input type="time" bind:value={techForm.shiftEnd} /></label>
          </div>
          <div class="row">
            <label>Break Start<input type="time" bind:value={techForm.breakStart} /></label>
            <label>Break End<input type="time" bind:value={techForm.breakEnd} /></label>
          </div>
          <label>Skills (comma-separated)<input bind:value={techForm.skills} placeholder="electrical, plumbing" /></label>
          <div class="row">
            <label>Max Orders<input type="number" bind:value={techForm.maxOrders} min="1" /></label>
            <label>Vehicle<select bind:value={techForm.vehicleType}>
              <option>van</option><option>car</option><option>truck</option><option>standard</option>
            </select></label>
          </div>
          <button type="submit" class="submit-btn">Add Technician</button>
        </form>
      {/if}
    {/if}

    {#if tab === 'orders'}
      <div class="list">
        {#each workOrders as order, i}
          <div class="item" class:editing={editingOrderId === order.id}>
            <div class="item-color" style="background:{PRIORITY_COLORS[order.priority]}"></div>
            <div class="item-body">
              <div class="item-name">{order.customer_name || order.id} <span class="num">#{i+1}</span></div>
              <div class="item-meta">{order.location.address || `${order.location.latitude}, ${order.location.longitude}`}</div>
              <div class="item-meta">{order.priority} · {order.work_type} · {order.service_time} min</div>
            </div>
            <button class="edit-btn" class:active={editingOrderId === order.id} on:click={() => editOrder(order)} title="Edit">✏</button>
            <button class="remove-btn" on:click={() => dispatch('removeWorkOrder', order.id)}>✕</button>
          </div>

          {#if editingOrderId === order.id}
            <form class="form" on:submit|preventDefault={submitOrder}>
              <div class="form-title">Edit Work Order</div>
              <label>Customer Name *<input bind:value={orderForm.customerName} placeholder="ABC Corp" required /></label>
              <div class="row">
                <label>Latitude *<input type="number" step="any" bind:value={orderForm.latitude} placeholder="3.1478" required /></label>
                <label>Longitude *<input type="number" step="any" bind:value={orderForm.longitude} placeholder="101.6159" required /></label>
              </div>
              <label>
                Address
                <div class="input-row">
                  <input bind:value={orderForm.address} placeholder="e.g. Damansara Heights" />
                  <button type="button" class="pick-btn" class:active={pickingLocation} on:click={pickOnMap} title="Click on map to pick">📍</button>
                </div>
              </label>
              <div class="row">
                <label>Priority<select bind:value={orderForm.priority}>
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                  <option value="emergency">Emergency</option>
                </select></label>
                <label>Work Type<select bind:value={orderForm.workType}>
                  <option value="maintenance">Maintenance</option>
                  <option value="repair">Repair</option>
                  <option value="inspection">Inspection</option>
                  <option value="installation">Installation</option>
                  <option value="emergency">Emergency</option>
                </select></label>
              </div>
              <label>Service Time (min)<input type="number" bind:value={orderForm.serviceTime} min="1" /></label>
              <label>Required Skills (comma-separated)<input bind:value={orderForm.skills} placeholder="electrical, plumbing" /></label>
              <label>Description<input bind:value={orderForm.description} placeholder="Brief description" /></label>
              <div class="form-actions">
                <button type="button" class="cancel-btn" on:click={cancelOrderEdit}>Cancel</button>
                <button type="submit" class="submit-btn">Save Changes</button>
              </div>
            </form>
          {/if}
        {/each}
        {#if workOrders.length === 0}
          <div class="empty">No work orders added</div>
        {/if}
      </div>

      <button class="add-btn" on:click={toggleOrderForm}>
        {showOrderForm ? '✕ Cancel' : '+ Add Work Order'}
      </button>

      {#if showOrderForm}
        <form class="form" on:submit|preventDefault={submitOrder}>
          <div class="form-title">New Work Order</div>
          <label>Customer Name *<input bind:value={orderForm.customerName} placeholder="ABC Corp" required /></label>
          <div class="row">
            <label>Latitude *<input type="number" step="any" bind:value={orderForm.latitude} placeholder="3.1478" required /></label>
            <label>Longitude *<input type="number" step="any" bind:value={orderForm.longitude} placeholder="101.6159" required /></label>
          </div>
          <label>
            Address
            <div class="input-row">
              <input bind:value={orderForm.address} placeholder="e.g. Damansara Heights" />
              <button type="button" class="pick-btn" class:active={pickingLocation} on:click={pickOnMap} title="Click on map to pick">📍</button>
            </div>
          </label>
          <div class="row">
            <label>Priority<select bind:value={orderForm.priority}>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
              <option value="critical">Critical</option>
              <option value="emergency">Emergency</option>
            </select></label>
            <label>Work Type<select bind:value={orderForm.workType}>
              <option value="maintenance">Maintenance</option>
              <option value="repair">Repair</option>
              <option value="inspection">Inspection</option>
              <option value="installation">Installation</option>
              <option value="emergency">Emergency</option>
            </select></label>
          </div>
          <label>Service Time (min)<input type="number" bind:value={orderForm.serviceTime} min="1" /></label>
          <label>Required Skills (comma-separated)<input bind:value={orderForm.skills} placeholder="electrical, plumbing" /></label>
          <label>Description<input bind:value={orderForm.description} placeholder="Brief description" /></label>
          <button type="submit" class="submit-btn">Add Work Order</button>
        </form>
      {/if}
    {/if}
  </div>
</aside>

<style>
  aside {
    width: 300px; flex-shrink: 0;
    background: #1a1d2e; border-right: 1px solid #2d3250;
    display: flex; flex-direction: column; overflow: hidden;
  }

  .tabs { display: flex; border-bottom: 1px solid #2d3250; flex-shrink: 0; }
  .tabs button {
    flex: 1; padding: 12px 8px; background: none; color: #8892b0;
    font-size: 13px; font-weight: 500; border-radius: 0; border-right: 1px solid #2d3250;
  }
  .tabs button:last-child { border-right: none; }
  .tabs button.active { color: #e0e6f0; background: #232640; border-bottom: 2px solid #6c63ff; }
  .tabs button:hover:not(.active) { background: #1f2235; color: #c0c8e0; }

  .badge {
    background: #2d3250; color: #8892b0; font-size: 11px;
    padding: 1px 6px; border-radius: 10px; margin-left: 4px;
  }

  .panel-content { flex: 1; overflow-y: auto; display: flex; flex-direction: column; padding: 8px; }

  .list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 8px; }

  .item {
    display: flex; align-items: flex-start; gap: 8px;
    background: #232640; border: 1px solid #2d3250; border-radius: 8px;
    padding: 10px; position: relative;
  }
  .item.editing { border-color: #6c63ff; }
  .item-color { width: 4px; flex-shrink: 0; border-radius: 2px; align-self: stretch; min-height: 30px; }
  .item-body { flex: 1; min-width: 0; }
  .item-name { font-size: 13px; font-weight: 600; color: #e0e6f0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .num { color: #8892b0; font-weight: 400; }
  .item-meta { font-size: 11px; color: #8892b0; margin-top: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  .edit-btn { background: none; color: #8892b0; font-size: 12px; padding: 2px 4px; flex-shrink: 0; }
  .edit-btn:hover, .edit-btn.active { color: #6c63ff; }
  .remove-btn { background: none; color: #8892b0; font-size: 13px; padding: 2px 4px; flex-shrink: 0; }
  .remove-btn:hover { color: #ff2d55; }

  .empty { color: #8892b0; font-size: 12px; text-align: center; padding: 16px 0; }

  .add-btn {
    width: 100%; padding: 9px; background: #232640; color: #6c63ff;
    border: 1px dashed #6c63ff; border-radius: 8px; font-size: 13px; font-weight: 600;
    margin-bottom: 8px; flex-shrink: 0;
  }
  .add-btn:hover { background: #2a2e55; }

  .form { display: flex; flex-direction: column; gap: 8px; background: #232640; border: 1px solid #6c63ff; border-radius: 8px; padding: 12px; margin-bottom: 4px; }

  .form-title { font-size: 12px; font-weight: 700; color: #6c63ff; margin-bottom: 2px; }

  label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #8892b0; }

  .row { display: flex; gap: 8px; }
  .row label { flex: 1; }

  .input-row { display: flex; gap: 6px; }
  .input-row input { flex: 1; }

  .pick-btn {
    background: #2d3250; color: #e0e6f0; padding: 7px 10px; border-radius: 6px; font-size: 14px; flex-shrink: 0;
  }
  .pick-btn.active { background: #6c63ff; }
  .pick-btn:hover { background: #6c63ff; }

  .form-actions { display: flex; gap: 8px; margin-top: 4px; }
  .cancel-btn { flex: 1; padding: 9px; background: #2d3250; color: #8892b0; font-size: 13px; font-weight: 600; border-radius: 6px; }
  .cancel-btn:hover { color: #e0e6f0; }
  .submit-btn { flex: 1; background: #6c63ff; color: #fff; padding: 9px; font-size: 13px; font-weight: 600; border-radius: 6px; }
  .submit-btn:hover { background: #5a52d5; }
</style>
