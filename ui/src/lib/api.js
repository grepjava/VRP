const BASE = 'http://localhost:8000'

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

export function minsToTime(m) {
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

export function timeToMins(t) {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}
