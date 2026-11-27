import { useCallback, useEffect, useState } from 'react'

export interface ApiState<T> {
  data: T | undefined
  error: Error | undefined
  loading: boolean
  /** Fetch again (e.g. from a "Retry" button). */
  reload: () => void
}

/**
 * Load data from the API on mount and on reload().
 * `load` must be stable (defined outside the component or wrapped in useCallback),
 * otherwise it is called on every render.
 */
export function useApi<T>(load: () => Promise<T>): ApiState<T> {
  const [state, setState] = useState<Omit<ApiState<T>, 'reload'>>({
    data: undefined,
    error: undefined,
    loading: true,
  })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let cancelled = false
    load()
      .then((data) => !cancelled && setState({ data, error: undefined, loading: false }))
      .catch((error: Error) => !cancelled && setState((s) => ({ ...s, error, loading: false })))
    return () => {
      cancelled = true
    }
  }, [load, attempt])

  const reload = useCallback(() => {
    setState((s) => ({ ...s, error: undefined, loading: true }))
    setAttempt((n) => n + 1)
  }, [])

  return { ...state, reload }
}
