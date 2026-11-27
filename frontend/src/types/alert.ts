import type { IsoDateTime } from './common'

export type AlertType = 'LOW_STOCK' | 'OUT_OF_STOCK'
export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type AlertStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'

/** Item of GET /api/alerts */
export interface Alert {
  id: number
  product_id: number
  product_sku: string
  product_name: string
  alert_type: AlertType
  severity: AlertSeverity
  message: string
  status: AlertStatus
  created_at: IsoDateTime
  resolved_at: IsoDateTime | null
}

/** Query parameters of GET /api/alerts */
export interface AlertListParams {
  status?: AlertStatus
  unresolved_only?: boolean
  alert_type?: AlertType
  severity?: AlertSeverity
  product_id?: number
  skip?: number
  limit?: number
}
