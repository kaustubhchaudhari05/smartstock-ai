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
    if (Array.isArray(body?.detail) && typeof body.detail[0]?.msg === 'string') return body.detail[0].msg
  } catch {
    // not JSON; fall through
  }
  return `Request failed (${response.status})`
}

export async function apiGet<T>(path: string, params?: QueryParams): Promise<T> {
  const url = `/api${path}${toQueryString(params)}`
  let response: Response
  try {
    response = await fetch(url, { headers: { Accept: 'application/json' } })
  } catch {
    throw new ApiError(0, 'Cannot reach the SmartStock server')
  }
  if (!response.ok) {
    throw new ApiError(response.status, await errorMessage(response))
  }
  return (await response.json()) as T
}
