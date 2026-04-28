// In Docker: VITE_API_URL is empty and nginx proxies /vrp/* → api:8000
// In dev:    set VITE_API_URL=http://localhost:8000 in ui/.env.local
const BASE = import.meta.env.VITE_API_URL ?? ''

export async function optimize(technicians, workOrders, config = null) {
  const body = { technicians, work_orders: workOrders }
  if (config) body.config = config
  const res = await fetch(`${BASE}/vrp/optimize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Server error ${res.status}`)
  }
  return res.json()
}

export async function listScenarios() {
  const res = await fetch(`${BASE}/vrp/scenarios`)
  if (!res.ok) throw new Error(`Server error ${res.status}`)
  return res.json()
}

export async function saveScenario(name, technicians, workOrders, city = '', source = 'manual') {
  const res = await fetch(`${BASE}/vrp/scenarios`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, technicians, work_orders: workOrders, city, source })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Server error ${res.status}`)
  }
  return res.json()
}

export async function loadScenario(slug) {
  const res = await fetch(`${BASE}/vrp/scenarios/${encodeURIComponent(slug)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Server error ${res.status}`)
  }
  return res.json()
}

export async function deleteScenario(slug) {
  const res = await fetch(`${BASE}/vrp/scenarios/${encodeURIComponent(slug)}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Server error ${res.status}`)
  }
  return res.json()
}

export async function generateDemo(city, numOrders, numTechnicians) {
  const res = await fetch(`${BASE}/vrp/generate-demo`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ city, num_orders: numOrders, num_technicians: numTechnicians })
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `Server error ${res.status}`)
  }
  return res.json()
}

export function minsToTime(m) {
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

export function timeToMins(t) {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}
