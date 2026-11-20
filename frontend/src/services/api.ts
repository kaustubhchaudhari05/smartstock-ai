/** Thin fetch wrapper for the SmartStock backend. Paths are relative to /api. */
export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`, { headers: { Accept: 'application/json' } })
  if (!response.ok) {
    throw new ApiError(response.status, `Request to /api${path} failed (${response.status})`)
  }
  return (await response.json()) as T
}
