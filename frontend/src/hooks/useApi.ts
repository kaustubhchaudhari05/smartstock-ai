import { useCallback, useEffect, useState } from 'react'

export interface ApiState<T> {
  /** Latest successful result; kept while a newer request is loading (no flicker). */
  data: T | undefined
  /** Error of the latest finished request (hidden while a new request is loading). */
  error: Error | undefined
  /** True while the shown data does not come from the current loader / attempt. */
  loading: boolean
  /** Fetch again (e.g. from a "Retry" button). */
  reload: () => void
}

interface Result<T> {
  data: T | undefined
  error: Error | undefined
  /** Which loader, refresh key and attempt produced this result. */
  source: (() => Promise<T>) | undefined
  key: unknown
  attempt: number
}

/**
 * Load data from the API whenever `load` or `refreshKey` changes, and on reload().
 * `load` must be stable (module-level, or useCallback with its real dependencies),
 * otherwise it is called on every render. Change `refreshKey` to refetch after a related
 * change elsewhere on the page (e.g. a recorded stock movement).
 */
export function useApi<T>(load: () => Promise<T>, refreshKey?: unknown): ApiState<T> {
  const [result, setResult] = useState<Result<T>>({
    data: undefined,
    error: undefined,
    source: undefined,
    key: undefined,
    attempt: 0,
  })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    load()
      .then(
        (data) => !cancelled && setResult({ data, error: undefined, source: load, key: refreshKey, attempt }),
      )
      .catch(
        (error: Error) =>
          !cancelled && setResult((r) => ({ ...r, error, source: load, key: refreshKey, attempt })),
      )
    return () => {
      cancelled = true
    }
  }, [load, refreshKey, attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  const loading = result.source !== load || result.key !== refreshKey || result.attempt !== attempt

  return { data: result.data, error: loading ? undefined : result.error, loading, reload }
}
