import type { ReactNode } from 'react'
import { Link } from 'react-router'

interface StatCardProps {
  label: string
  value: ReactNode
  icon: string
  /** Bootstrap color for the icon, e.g. "primary", "warning". */
  color?: string
  hint?: ReactNode
  to?: string
}

/** One headline number on the dashboard; links to the page with the details. */
export default function StatCard({ label, value, icon, color = 'primary', hint, to }: StatCardProps) {
  const body = (
    <div className="card-body d-flex align-items-start gap-3">
      <span className={`stat-icon text-${color} bg-${color}-subtle`} aria-hidden="true">
        <i className={`bi bi-${icon}`} />
      </span>
      <div className="min-w-0">
        <div className="text-body-secondary small">{label}</div>
        <div className="fs-4 fw-semibold lh-sm">{value}</div>
        {hint && <div className="small text-body-secondary mt-1">{hint}</div>}
      </div>
    </div>
  )
  return to ? (
    <Link to={to} className="card h-100 text-decoration-none stat-card">
      {body}
    </Link>
  ) : (
    <div className="card h-100">{body}</div>
  )
}
