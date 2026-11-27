import type { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: string
  title: string
  message?: string
  action?: ReactNode
}

/** Shown when a list or page has nothing to display. */
export default function EmptyState({ icon = 'inbox', title, message, action }: EmptyStateProps) {
  return (
    <div className="text-center text-body-secondary py-5">
      <i className={`bi bi-${icon} display-6 d-block mb-3`} aria-hidden="true" />
      <p className="fw-semibold text-body mb-1">{title}</p>
      {message && <p className="mb-3">{message}</p>}
      {action}
    </div>
  )
}
