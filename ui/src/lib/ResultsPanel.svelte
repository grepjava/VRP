<script>
  import { minsToTime } from './api.js'

  export let result = null
  export let technicians = []
  export let workOrders = []
  export let ROUTE_COLORS = []

  $: unassigned = result?.unassigned_orders ?? []
  $: routes = result?.routes?.filter(r => r.assignments?.length) ?? []

  function getTechName(id) {
    return technicians.find(t => t.id === id)?.name ?? id
  }

  function getOrderName(id) {
    const o = workOrders.find(o => o.id === id)
    return o ? (o.customer_name || id) : id
  }

  function fmtMins(m) {
    if (m < 60) return `${m}m`
    return `${Math.floor(m / 60)}h ${m % 60}m`
  }
</script>

{#if result}
  <div class="panel">
    <!-- Summary bar -->
    <div class="summary">
      <div class="stat" class:good={result.status === 'success'} class:warn={result.status !== 'success'}>
        <span class="label">Status</span>
        <span class="value">{result.status}</span>
      </div>
      <div class="stat">
        <span class="label">Completed</span>
        <span class="value">{result.orders_completed} / {workOrders.length}</span>
      </div>
      <div class="stat">
        <span class="label">Unassigned</span>
        <span class="value" class:warn={unassigned.length > 0}>{unassigned.length}</span>
      </div>
      <div class="stat">
        <span class="label">Technicians Used</span>
        <span class="value">{result.technicians_used}</span>
      </div>
      <div class="stat">
        <span class="label">Total Travel</span>
        <span class="value">{fmtMins(result.total_travel_time)}</span>
      </div>
      <div class="stat">
        <span class="label">Solve Time</span>
        <span class="value">{result.solve_time?.toFixed(2)}s</span>
      </div>
      {#if result.memory_info}
        <div class="stat">
          <span class="label">GPU Mem</span>
          <span class="value">{result.memory_info.gpu_used_mb?.toFixed(0)} MB</span>
        </div>
      {/if}
    </div>

    <!-- Routes -->
    <div class="routes">
      {#each routes as route, i}
        {@const tech = technicians.find(t => t.id === route.technician_id)}
        {@const techIdx = technicians.findIndex(t => t.id === route.technician_id)}
        {@const color = ROUTE_COLORS[(techIdx >= 0 ? techIdx : i) % ROUTE_COLORS.length]}
        {@const sorted = route.assignments.filter(a => !a.work_order_id?.startsWith('break')).sort((a,b) => a.sequence_order - b.sequence_order)}
        <div class="route">
          <div class="route-header" style="border-left: 3px solid {color}">
            <span class="route-tech">{tech?.name ?? route.technician_id}</span>
            <span class="route-meta">{sorted.length} orders · {fmtMins(route.total_travel_time)} travel · {fmtMins(route.total_service_time)} service</span>
          </div>
          <div class="assignments">
            {#each sorted as a, j}
              <div class="assignment">
                <span class="seq" style="background:{color}">{j + 1}</span>
                <span class="asgn-name">{getOrderName(a.work_order_id)}</span>
                <span class="asgn-time">{minsToTime(a.start_time)} – {minsToTime(a.finish_time)}</span>
                <span class="asgn-travel">+{a.travel_time_to}m travel</span>
              </div>
            {/each}
          </div>
        </div>
      {/each}

      {#if unassigned.length > 0}
        <div class="route unassigned-block">
          <div class="route-header" style="border-left: 3px solid #ff2d55">
            <span class="route-tech" style="color:#ff2d55">⚠ Unassigned</span>
            <span class="route-meta">{unassigned.length} orders could not be scheduled</span>
          </div>
          <div class="assignments">
            {#each unassigned as id}
              <div class="assignment">
                <span class="asgn-name">{getOrderName(id)}</span>
              </div>
            {/each}
          </div>
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
  .panel {
    border-top: 1px solid #2d3250;
    background: #1a1d2e;
    flex-shrink: 0;
    max-height: 220px;
    display: flex;
    flex-direction: column;
  }

  .summary {
    display: flex; gap: 0; border-bottom: 1px solid #2d3250; flex-shrink: 0; overflow-x: auto;
  }
  .stat {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: 8px 16px; border-right: 1px solid #2d3250; min-width: 90px;
  }
  .label { font-size: 10px; color: #8892b0; text-transform: uppercase; letter-spacing: 0.5px; }
  .value { font-size: 16px; font-weight: 700; color: #e0e6f0; margin-top: 2px; }
  .value.warn { color: #ff6b35; }
  .stat.good .value { color: #30d158; }
  .stat.warn .value { color: #ff6b35; }

  .routes {
    display: flex; gap: 8px; padding: 8px; overflow-x: auto; flex: 1; align-items: flex-start;
  }

  .route {
    background: #232640; border: 1px solid #2d3250; border-radius: 8px;
    min-width: 220px; max-width: 260px; flex-shrink: 0; overflow: hidden;
  }

  .route-header {
    padding: 7px 10px; display: flex; flex-direction: column; gap: 2px;
    background: #1e2138;
  }
  .route-tech { font-size: 13px; font-weight: 700; color: #e0e6f0; }
  .route-meta { font-size: 11px; color: #8892b0; }

  .assignments { padding: 6px; display: flex; flex-direction: column; gap: 4px; }

  .assignment {
    display: flex; align-items: center; gap: 6px; font-size: 11px;
    background: #1a1d2e; border-radius: 5px; padding: 5px 7px;
  }
  .seq {
    width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center;
    justify-content: center; font-size: 10px; font-weight: 700; color: #fff; flex-shrink: 0;
  }
  .asgn-name { flex: 1; color: #c0c8e0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .asgn-time { color: #6c63ff; white-space: nowrap; }
  .asgn-travel { color: #8892b0; white-space: nowrap; }
</style>
