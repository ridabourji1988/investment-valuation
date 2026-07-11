// Thin API client.
const base = ''

async function get(path) {
  const r = await fetch(base + path)
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail || detail } catch (_) {}
    throw new Error(detail)
  }
  return r.json()
}

export const api = {
  health: () => get('/api/health'),
  feed: () => get('/api/feed'),
  brief: () => get('/api/brief'),
  asset: (t) => get(`/api/asset/${t}`),
  narrative: (t) => get(`/api/asset/${t}/narrative`),
  macro: () => get('/api/macro'),
  rateSensitivity: (bp = 50) => get(`/api/macro/rate-sensitivity?bp=${bp}`),
  formulas: () => get('/api/formulas'),
  search: (q) => get(`/api/search?q=${encodeURIComponent(q)}`),
  retry: () => fetch(base + '/api/retry', { method: 'POST' }).then((r) => r.json()),
}
