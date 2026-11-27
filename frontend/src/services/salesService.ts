import type { Sale, SaleCreate, SaleRecorded, SalesAnalytics } from '../types/sales'
import { apiGet, apiPost } from './api'

export const getSalesAnalytics = (params?: { product_id?: number; include_inactive?: boolean }) =>
  apiGet<SalesAnalytics>('/sales/analytics', params)

export const listSales = (params?: { product_id?: number; date_from?: string; date_to?: string; skip?: number; limit?: number }) =>
  apiGet<Sale[]>('/sales', params)

/** Records the sale and its STOCK_OUT movement atomically; refused if stock is insufficient. */
export const recordSale = (data: SaleCreate) => apiPost<SaleRecorded>('/sales', data)
