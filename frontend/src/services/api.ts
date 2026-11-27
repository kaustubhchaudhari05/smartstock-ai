/** Thin fetch wrapper for the SmartStock backend. Paths are relative to /api. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export type QueryParams = Record<string, string | number | boolean | null | undefined>

/** "?a=1&b=x" from the defined params (undefined / null / "" are left out). */
export function toQueryString(params?: QueryParams): string {
  if (!params) return ''
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `?${query}` : ''
}

/** The backend's error message: `{"detail": "..."}`, or the first validation error. */
async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json()
    if (typeof body?.detail === 'string') return body.detail
    // FastAPI validation errors: [{loc: ["body", "unit_cost"], msg: "..."}]
    const first = Array.isArray(body?.detail) ? body.detail[0] : undefined
    if (typeof first?.msg === 'string') {
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : undefined
      return typeof field === 'string' && field !== 'body' ? `${field}: ${first.msg}` : first.msg
    }
  } catch {
    // not JSON; fall through
  }
  return `Request failed (${response.status})`
}

async function request<T>(method: string, path: string, params?: QueryParams, body?: unknown): Promise<T> {
  const url = `/api${path}${toQueryString(params)}`
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Cannot reach the SmartStock server')
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  return (await response.json()) as T
}

export const apiGet = <T>(path: string, params?: QueryParams) => request<T>('GET', path, params)

export const apiPost = <T>(path: string, body: unknown) => request<T>('POST', path, undefined, body)

export const apiPut = <T>(path: string, body: unknown) => request<T>('PUT', path, undefined, body)

export const apiPatch = <T>(path: string, body: unknown) => request<T>('PATCH', path, undefined, body)

export const apiDelete = <T>(path: string) => request<T>('DELETE', path)
