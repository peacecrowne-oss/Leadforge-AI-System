const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

export function getToken() { return localStorage.getItem('token') }
export function setToken(t) { localStorage.setItem('token', t) }
export function clearToken() { localStorage.removeItem('token') }

export function getUserPlan() {
  const token = getToken()
  if (!token) return 'free'
  try {
    const parts = token.split('.')
    if (parts.length < 3) return 'free'
    // JWTs use base64url: replace url-safe chars and restore padding
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64 + '='.repeat((4 - (base64.length % 4)) % 4)
    const payload = JSON.parse(atob(padded))
    return payload.plan || 'free'
  } catch {
    return 'free'
  }
}

function getAuthHeaders() {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function register(email, password) {
  const res = await fetch(`${BASE_URL}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw Object.assign(new Error(err.detail || res.statusText), { status: res.status })
  }
  return res.json()
}

export async function login(email, password) {
  const body = new URLSearchParams({ username: email, password })
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw Object.assign(new Error(err.detail || res.statusText), { status: res.status })
  }
  const data = await res.json()
  return data.access_token
}

export async function apiGet(path) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { ...getAuthHeaders() },
  })
  if (!res.ok) throw Object.assign(new Error(res.statusText), { status: res.status })
  return res.json()
}

export async function apiPost(path, body) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw Object.assign(new Error(res.statusText), { status: res.status })
  return res.json()
}

export async function apiDelete(path) {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'DELETE',
    headers: { ...getAuthHeaders() },
  })
  if (!res.ok) throw Object.assign(new Error(res.statusText), { status: res.status })
  return res.status === 204 ? null : res.json()
}

export async function healthCheck() {
  return apiGet('/health')
}
