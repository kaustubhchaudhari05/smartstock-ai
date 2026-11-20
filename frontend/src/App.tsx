import { useEffect, useState } from 'react'
import { getAppHealth, getDatabaseHealth } from './services/healthService'

type CheckState = { state: 'loading' } | { state: 'ok'; detail: string } | { state: 'error'; detail: string }

function StatusRow({ label, check }: { label: string; check: CheckState }) {
  const text = check.state === 'loading' ? 'Checking…' : check.detail
  return (
    <li className={`status-row status-${check.state}`}>
      <span className="status-dot" aria-hidden="true" />
      <span className="status-label">{label}</span>
      <span className="status-detail">{text}</span>
    </li>
  )
}

function App() {
  const [api, setApi] = useState<CheckState>({ state: 'loading' })
  const [db, setDb] = useState<CheckState>({ state: 'loading' })

  useEffect(() => {
    getAppHealth()
      .then((h) => setApi({ state: 'ok', detail: `${h.status} (${h.environment})` }))
      .catch(() => setApi({ state: 'error', detail: 'Backend unreachable' }))

    getDatabaseHealth()
      .then((h) => setDb({ state: 'ok', detail: h.database }))
      .catch(() => setDb({ state: 'error', detail: 'Database unreachable' }))
  }, [])

  return (
    <main className="container">
      <h1>SmartStock AI</h1>
      <p className="subtitle">Inventory monitoring and replenishment assistant</p>
      <section className="card">
        <h2>System status</h2>
        <ul className="status-list">
          <StatusRow label="API" check={api} />
          <StatusRow label="Database" check={db} />
        </ul>
      </section>
    </main>
  )
}

export default App
