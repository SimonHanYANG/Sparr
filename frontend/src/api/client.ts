/** Minimal API client: JWT auth, JSON, one-shot refresh on 401 (PLAN.md §6). */
const ACCESS_KEY = 'sparr_access'
const REFRESH_KEY = 'sparr_refresh'

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY)
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(ACCESS_KEY, access)
  localStorage.setItem(REFRESH_KEY, refresh)
}

export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

export class ApiError extends Error {
  status: number
  /** Parsed DRF error body: { field: [messages] } or { detail: msg } */
  detail: Record<string, unknown>
  constructor(status: number, message: string, detail: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.detail = detail
  }
}

async function tryRefresh(): Promise<boolean> {
  const refresh = localStorage.getItem(REFRESH_KEY)
  if (!refresh) return false
  const resp = await fetch('/api/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  if (!resp.ok) return false
  const data = await resp.json()
  localStorage.setItem(ACCESS_KEY, data.access)
  if (data.refresh) localStorage.setItem(REFRESH_KEY, data.refresh)
  return true
}

export async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const doFetch = () =>
    fetch(path, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
        ...options.headers,
      },
    })

  let resp = await doFetch()
  if (resp.status === 401 && (await tryRefresh())) {
    resp = await doFetch()
  }
  if (!resp.ok) {
    let detail: Record<string, unknown> = {}
    try {
      const body = await resp.json()
      if (typeof body === 'object' && body !== null) {
        detail = body as Record<string, unknown>
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, `HTTP ${resp.status}`, detail)
  }
  if (resp.status === 204) return undefined as T
  return (await resp.json()) as T
}

/** multipart upload with the same JWT/refresh semantics as apiFetch. */
export async function apiUpload<T>(path: string, form: FormData): Promise<T> {
  const doFetch = () =>
    fetch(path, {
      method: 'POST',
      headers: getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {},
      body: form,
    })
  let resp = await doFetch()
  if (resp.status === 401 && (await tryRefresh())) {
    resp = await doFetch()
  }
  if (!resp.ok) {
    let detail: Record<string, unknown> = {}
    try {
      const body = await resp.json()
      if (typeof body === 'object' && body !== null) {
        detail = body as Record<string, unknown>
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(resp.status, `HTTP ${resp.status}`, detail)
  }
  return (await resp.json()) as T
}

/** SSE-over-fetch: invoke onEvent per server-sent event (event + JSON data). */
export async function apiStream(
  path: string,
  body: unknown,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const doFetch = () =>
    fetch(path, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(getAccessToken() ? { Authorization: `Bearer ${getAccessToken()}` } : {}),
      },
      body: JSON.stringify(body ?? {}),
    })
  let resp = await doFetch()
  if (resp.status === 401 && (await tryRefresh())) {
    resp = await doFetch()
  }
  if (!resp.ok || !resp.body) {
    throw new ApiError(resp.status, `HTTP ${resp.status}`)
  }
  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      let event = 'message'
      const dataLines: string[] = []
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
      }
      if (dataLines.length) {
        try {
          onEvent(event, JSON.parse(dataLines.join('\n')))
        } catch {
          /* ignore malformed frames */
        }
      }
    }
  }
}
