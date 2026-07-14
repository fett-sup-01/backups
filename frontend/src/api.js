// Cliente HTTP do dashboard. Mesma origem: nginx faz proxy de /api -> FastAPI.
const BASE = '/api'

export function getToken() {
  return localStorage.getItem('token')
}
export function setToken(t) {
  if (t) localStorage.setItem('token', t)
  else localStorage.removeItem('token')
}

export async function api(method, path, body) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const t = getToken()
  if (t) headers['Authorization'] = 'Bearer ' + t

  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let data
  try {
    data = text ? JSON.parse(text) : {}
  } catch {
    data = { detail: text }
  }
  if (!res.ok) {
    const err = new Error(data.detail || ('HTTP ' + res.status))
    err.status = res.status
    throw err
  }
  return data
}
