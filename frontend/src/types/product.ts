import type { DecimalString, IsoDateTime } from './common'
import type { InventoryStatus } from './inventory'

/** Response of GET /api/products and GET /api/products/{id} */
export interface Product {
  id: number
  sku: string
  name: string
  category: string
  description: string | null
  current_stock: number
  reorder_point: number
  minimum_stock: number
  reorder_quantity: number
  unit_cost: DecimalString
  supplier_id: number | null
  supplier: { id: number; name: string } | null
  is_active: boolean
  /** Computed by the backend on read. */
  inventory_status: InventoryStatus
  created_at: IsoDateTime
  updated_at: IsoDateTime
}

/** Query parameters of GET /api/products */
export interface ProductListParams {
  search?: string
  category?: string
  supplier_id?: number
  include_inactive?: boolean
  skip?: number
  limit?: number
}

/** Body of POST /api/products. `current_stock` is the opening stock. */
export interface ProductCreate {
  sku: string
  name: string
  category: string
  description?: string | null
  current_stock?: number
  reorder_point: number
  minimum_stock: number
  reorder_quantity: number
  unit_cost: DecimalString
  supplier_id?: number | null
}

/** Body of PUT /api/products/{id}: only the fields sent are changed; stock is not editable here. */
export type ProductUpdate = Partial<Omit<ProductCreate, 'current_stock'>> & { is_active?: boolean }
