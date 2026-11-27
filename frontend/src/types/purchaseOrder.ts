import type { DecimalString } from './common'

export type PurchaseOrderStatus =
  | 'DRAFT'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'REJECTED'
  | 'SENT'
  | 'RECEIVED'
  | 'CANCELLED'

export interface PurchaseOrderStatusTotal {
  status: PurchaseOrderStatus
  order_count: number
  total_amount: DecimalString
}

/** Response of GET /api/purchase-orders/summary (all values computed by the backend). */
export interface PurchaseOrderSummary {
  awaiting_decision_count: number
  awaiting_decision_amount: DecimalString
  approved_count: number
  approved_amount: DecimalString
  total_orders: number
  by_status: PurchaseOrderStatusTotal[]
}
