import type { DecimalString, IsoDateTime } from './common'

export type InventoryStatus = 'HEALTHY' | 'LOW_STOCK' | 'OUT_OF_STOCK'

/** `summary` of GET /api/inventory (also the shape of each `categories[]` entry, plus `category`). */
export interface InventorySummary {
  total_products: number
  total_units: number
  total_stock_value: DecimalString
  healthy_count: number
  low_stock_count: number
  out_of_stock_count: number
  reorder_needed_count: number
  replenishment_cost: DecimalString
}

export interface CategorySummary extends InventorySummary {
  category: string
}

export interface InventoryItem {
  product_id: number
  sku: string
  name: string
  category: string
  is_active: boolean
  current_stock: number
  reorder_point: number
  minimum_stock: number
  reorder_quantity: number
  unit_cost: DecimalString
  stock_value: DecimalString
  inventory_status: InventoryStatus
  supplier_id: number | null
  last_stock_update: IsoDateTime | null
}

/** Response of GET /api/inventory */
export interface InventoryOverview {
  summary: InventorySummary
  categories: CategorySummary[]
  items: InventoryItem[]
}

export type TransactionType = 'STOCK_IN' | 'STOCK_OUT' | 'ADJUSTMENT' | 'RETURN'

/** Item of GET /api/inventory/transactions (and `recent_transactions`). */
export interface InventoryTransaction {
  id: number
  product_id: number
  product_sku: string
  product_name: string
  transaction_type: TransactionType
  quantity: number
  /** Signed effect on current_stock, computed by the backend. */
  stock_change: number
  reference: string | null
  notes: string | null
  created_at: IsoDateTime
}

/** Response of GET /api/inventory/{product_id} */
export interface ProductInventoryDetail extends InventoryItem {
  recent_transactions: InventoryTransaction[]
}

/** Query parameters of GET /api/inventory/transactions */
export interface TransactionListParams {
  product_id?: number
  transaction_type?: TransactionType
  /** Inclusive, ISO 8601 with timezone. */
  date_from?: IsoDateTime
  /** Exclusive, ISO 8601 with timezone. */
  date_to?: IsoDateTime
  skip?: number
  limit?: number
}

/**
 * Body of POST /api/inventory/transactions. STOCK_IN / STOCK_OUT / RETURN take a positive
 * quantity; ADJUSTMENT is signed (+ adds, - removes) and may not be 0.
 */
export interface StockMovementCreate {
  product_id: number
  transaction_type: TransactionType
  quantity: number
  reference?: string | null
  notes?: string | null
}

/** Response of POST /api/inventory/transactions */
export interface StockMovementResult {
  transaction: InventoryTransaction
  previous_stock: number
  current_stock: number
}
