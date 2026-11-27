import { humanize } from '../utils/format'

/** Which vocabulary a value belongs to (some words, e.g. REJECTED, appear in several). */
export type BadgeKind =
  | 'inventory'
  | 'severity'
  | 'risk'
  | 'alertStatus'
  | 'urgency'
  | 'recommendationStatus'
  | 'purchaseOrder'
  | 'transactionType'

const LEVEL = { LOW: 'secondary', MEDIUM: 'info', HIGH: 'warning', CRITICAL: 'danger' }

const COLORS: Record<BadgeKind, Record<string, string>> = {
  inventory: { HEALTHY: 'success', LOW_STOCK: 'warning', OUT_OF_STOCK: 'danger' },
  severity: LEVEL,
  risk: LEVEL,
  alertStatus: { OPEN: 'danger', ACKNOWLEDGED: 'secondary', RESOLVED: 'success' },
  urgency: { IMMEDIATE: 'danger', SOON: 'warning', ROUTINE: 'info', NONE: 'secondary' },
  recommendationStatus: { PENDING_REVIEW: 'primary', ACCEPTED: 'success', REJECTED: 'secondary' },
  purchaseOrder: {
    DRAFT: 'secondary',
    PENDING_APPROVAL: 'warning',
    APPROVED: 'success',
    REJECTED: 'danger',
    SENT: 'info',
    RECEIVED: 'primary',
    CANCELLED: 'dark',
  },
  transactionType: { STOCK_IN: 'success', STOCK_OUT: 'danger', ADJUSTMENT: 'warning', RETURN: 'info' },
}

interface StatusBadgeProps {
  kind: BadgeKind
  value: string
  /** Text before the value, e.g. "Risk" -> "Risk: Critical". */
  prefix?: string
}

export default function StatusBadge({ kind, value, prefix }: StatusBadgeProps) {
  const color = COLORS[kind][value] ?? 'secondary'
  const label = humanize(value)
  return (
    <span className={`badge text-bg-${color}`}>
      {prefix ? `${prefix}: ${label}` : label}
    </span>
  )
}
