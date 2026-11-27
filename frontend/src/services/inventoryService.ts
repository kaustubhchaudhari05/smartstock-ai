import type {
  InventoryOverview,
  InventoryTransaction,
  ProductInventoryDetail,
  StockMovementCreate,
  StockMovementResult,
  TransactionListParams,
} from '../types/inventory'
import { apiGet, apiPost } from './api'

export const getInventoryOverview = (params?: { category?: string; include_inactive?: boolean }) =>
  apiGet<InventoryOverview>('/inventory', params)

export const getProductInventory = (productId: number) =>
  apiGet<ProductInventoryDetail>(`/inventory/${productId}`)

export const listTransactions = (params?: TransactionListParams) =>
  apiGet<InventoryTransaction[]>('/inventory/transactions', { ...params })

/** Record a stock movement; the backend validates it and returns previous / new stock. */
export const recordMovement = (data: StockMovementCreate) =>
  apiPost<StockMovementResult>('/inventory/transactions', data)
