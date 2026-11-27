import type { DecimalString, IsoDateTime } from './common'

export type SalesTrend = 'INCREASING' | 'STABLE' | 'DECREASING' | 'INSUFFICIENT_DATA'

export interface DailySales {
  /** UTC calendar day, "YYYY-MM-DD". */
  date: string
  units_sold: number
}

/** Per-product metrics of GET /api/sales/analytics (all computed by the backend). */
export interface ProductSalesMetrics {
  product_id: number
  sku: string
  name: string
  current_stock: number
  units_sold_total: number
  units_sold_7d: number
  units_sold_30d: number
  average_daily_sales_7d: DecimalString
  /** 30-day average daily demand. */
  average_daily_sales: DecimalString
  /** null when there were no sales in the 30-day window. */
  days_remaining: DecimalString | null
  trend: SalesTrend
  /** 30 days, oldest first, today partial; only when a single product is requested. */
  daily_sales: DailySales[] | null
}

export interface SalesAnalytics {
  as_of: IsoDateTime
  definitions: {
    short_window_days: number
    long_window_days: number
    trend_threshold: DecimalString
    windows: string
  }
  summary: {
    products: number
    units_sold_7d: number
    units_sold_30d: number
    increasing: number
    stable: number
    decreasing: number
    insufficient_data: number
  }
  products: ProductSalesMetrics[]
}

/** Item of GET /api/sales */
export interface Sale {
  id: number
  product_id: number
  product_sku: string
  product_name: string
  quantity_sold: number
  unit_price: DecimalString
  /** quantity_sold x unit_price, computed by the backend. */
  total_amount: DecimalString
  sale_date: IsoDateTime
  reference: string | null
}

/** Body of POST /api/sales */
export interface SaleCreate {
  product_id: number
  quantity_sold: number
  unit_price: DecimalString
  /** Defaults to now; must include a timezone and not be in the future. */
  sale_date?: IsoDateTime
  reference?: string | null
}

/** Response of POST /api/sales */
export interface SaleRecorded {
  sale: Sale
  inventory_transaction_id: number
  previous_stock: number
  current_stock: number
}
