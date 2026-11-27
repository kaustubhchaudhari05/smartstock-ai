import { useEffect, useState } from 'react'
import { getAppHealth, getDatabaseHealth } from '../services/healthService'

type Check = 'checking' | 'ok' | 'down'

const REFRESH_MS = 60_000

function Indicator({ label, check }: { label: string; check: Check }) {
  const color = check === 'ok' ? 'success' : check === 'down' ? 'danger' : 'secondary'
  const title = check === 'checking' ? 'Checking…' : check === 'ok' ? 'Connected' : 'Unreachable'
  return (
    <span className="d-inline-flex align-items-center gap-1" title={`${label}: ${title}`}>
      <span className={`status-dot bg-${color}`} aria-hidden="true" />
      <span className="small text-body-secondary">{label}</span>
      <span className="visually-hidden">{title}</span>
    </span>
  )
}

/** Small API / database connectivity indicator for the top bar (re-checked every minute). */
export default function ApiStatus() {
  const [api, setApi] = useState<Check>('checking')
  const [db, setDb] = useState<Check>('checking')

  useEffect(() => {
    let cancelled = false
    const check = () => {
      getAppHealth()
        .then(() => !cancelled && setApi('ok'))
        .catch(() => !cancelled && setApi('down'))
      getDatabaseHealth()
        .then(() => !cancelled && setDb('ok'))
        .catch(() => !cancelled && setDb('down'))
    }
    check()
    const timer = window.setInterval(check, REFRESH_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  return (
    <div className="d-flex align-items-center gap-3" aria-label="System status">
      <Indicator label="API" check={api} />
      <Indicator label="Database" check={db} />
    </div>
  )
}
