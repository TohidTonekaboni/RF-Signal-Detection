import { ApiError } from './errors.js'
import { useAuthStore } from '@/features/auth/authStore.js'
import { mockRequest } from './mock.js'

export const MOCK = import.meta.env.VITE_MOCK === 'true'
const BASE = '/api'

function buildUrl(path, query) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query || {})) if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  const s = qs.toString()
  return `${BASE}${path}${s ? `?${s}` : ''}`
}

let refreshing = null
/** Single-flight token refresh. Returns true on success. */
export function refreshSession() {
  if (!refreshing) {
    refreshing = rawRequest('POST', '/auth/refresh', { noRefresh: true })
      .then((data) => { useAuthStore.getState().setSession(data.access_token, data.user); return true })
      .catch(() => { useAuthStore.getState().clear(); return false })
      .finally(() => { refreshing = null })
  }
  return refreshing
}

async function rawRequest(method, path, { query, body, headers = {}, signal } = {}) {
  if (MOCK) return mockRequest(method, path, { query, body, headers })
  const token = useAuthStore.getState().accessToken
  const init = { method, credentials: 'include', signal, headers: { Accept: 'application/json', ...headers } }
  if (token) init.headers.Authorization = `Bearer ${token}`
  if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body) }
  let res
  try { res = await fetch(buildUrl(path, query), init) } catch { throw new ApiError(0, 'network') }
  if (res.status === 204) return null
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, data?.code || (res.status === 401 ? 'unauthorized' : 'unknown'), data?.message, data)
  const etag = res.headers.get('ETag')
  if (etag && data && typeof data === 'object') data.__etag = etag
  return data
}

/**
 * Single API entry point: attaches the access token, refreshes once on 401,
 * and surfaces backend error `code`s via ApiError.
 */
export async function api(method, path, opts = {}) {
  try {
    return await rawRequest(method, path, opts)
  } catch (err) {
    if (err instanceof ApiError && err.status === 401 && !opts.noRefresh && !path.startsWith('/auth/')) {
      if (await refreshSession()) return rawRequest(method, path, opts)
      window.location.assign(`${import.meta.env.BASE_URL}login`)
    }
    throw err
  }
}

export const get = (p, q, o) => api('GET', p, { query: q, ...o })
export const post = (p, body, o) => api('POST', p, { body, ...o })
export const put = (p, body, o) => api('PUT', p, { body, ...o })
export const patch = (p, body, o) => api('PATCH', p, { body, ...o })
export const del = (p, o) => api('DELETE', p, o)
