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
