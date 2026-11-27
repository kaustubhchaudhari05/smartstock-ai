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
  /** Which loader and attempt produced this result. */
  source: (() => Promise<T>) | undefined
  attempt: number
}

/**
 * Load data from the API whenever `load` changes and on reload().
 * `load` must be stable (module-level, or useCallback with its real dependencies),
 * otherwise it is called on every render.
 */
export function useApi<T>(load: () => Promise<T>): ApiState<T> {
  const [result, setResult] = useState<Result<T>>({
    data: undefined,
    error: undefined,
    source: undefined,
    attempt: 0,
  })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    load()
      .then((data) => !cancelled && setResult({ data, error: undefined, source: load, attempt }))
      .catch(
        (error: Error) => !cancelled && setResult((r) => ({ ...r, error, source: load, attempt })),
      )
    return () => {
      cancelled = true
    }
  }, [load, attempt])

  const reload = useCallback(() => setAttempt((n) => n + 1), [])
  const loading = result.source !== load || result.attempt !== attempt

  return { data: result.data, error: loading ? undefined : result.error, loading, reload }
}
