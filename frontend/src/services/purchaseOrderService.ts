import type { PurchaseOrderSummary } from '../types/purchaseOrder'
import { apiGet } from './api'

export const getPurchaseOrderSummary = (params?: { supplier_id?: number }) =>
  apiGet<PurchaseOrderSummary>('/purchase-orders/summary', params)
