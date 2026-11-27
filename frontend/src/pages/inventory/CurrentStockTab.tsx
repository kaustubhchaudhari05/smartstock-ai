import { useCallback, useState } from 'react'
import { Link } from 'react-router'
import EmptyState from '../../components/EmptyState'
import ErrorState from '../../components/ErrorState'
import LoadingState from '../../components/LoadingState'
import StatusBadge from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { getInventoryOverview } from '../../services/inventoryService'
import type { InventoryStatus } from '../../types/inventory'
import { formatMoney, formatNumber, formatRelativeTime } from '../../utils/format'

interface CurrentStockTabProps {
  categories: string[]
  /** Changes after a movement is recorded, to refetch. */
  refreshKey: number
  onRecord: (productId: number) => void
}

const STATUS_FILTERS: { value: '' | InventoryStatus; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'OUT_OF_STOCK', label: 'Out of stock' },
  { value: 'LOW_STOCK', label: 'Low stock' },
  { value: 'HEALTHY', label: 'Healthy' },
]

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <div className="col-6 col-md-3">
      <div className="small text-body-secondary">{label}</div>
      <div className="fs-5 fw-semibold">{value}</div>
    </div>
  )
}

export default function CurrentStockTab({ categories, refreshKey, onRecord }: CurrentStockTabProps) {
  const [category, setCategory] = useState('')
  const [status, setStatus] = useState<'' | InventoryStatus>('')

  // Category filtering and every figure come from the backend.
  const load = useCallback(
    () => getInventoryOverview({ category: category || undefined }),
    [category],
  )
  const { data, error, loading, reload } = useApi(load, refreshKey)
  // The status filter only hides rows; the status itself is computed by the backend.
  const items = (data?.items ?? []).filter((i) => !status || i.inventory_status === status)
  const s = data?.summary

  return (
    <div className="card">
      <div className="card-body border-bottom">
        <div className="row g-2 mb-3">
          <div className="col-6 col-md-4">
            <select className="form-select" aria-label="Category" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
          <div className="col-6 col-md-4">
            <select className="form-select" aria-label="Stock status" value={status}
              onChange={(e) => setStatus(e.target.value as '' | InventoryStatus)}>
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>{f.label}</option>
              ))}
            </select>
          </div>
        </div>
        {s && (
          <div className="row g-3">
            <Figure label="Units in stock" value={formatNumber(s.total_units)} />
            <Figure label="Stock value" value={formatMoney(s.total_stock_value)} />
            <Figure label="Low / out of stock" value={`${formatNumber(s.low_stock_count)} / ${formatNumber(s.out_of_stock_count)}`} />
            <Figure label="Cost to reorder" value={formatMoney(s.replenishment_cost)} />
          </div>
        )}
      </div>

      {error && (
        <div className="card-body">
          <ErrorState error={error} onRetry={reload} />
        </div>
      )}
      {!data && loading && <LoadingState label="Loading stock…" />}
      {data && items.length === 0 && (
        <EmptyState icon="boxes" title="No products match" message="Try another category or status." />
      )}
      {data && items.length > 0 && (
        <>
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0">
              <thead>
                <tr>
                  <th scope="col">Product</th>
                  <th scope="col" className="text-end">Stock</th>
                  <th scope="col">Status</th>
                  <th scope="col" className="text-end d-none d-md-table-cell" title="Reorder point / minimum stock">Reorder / min</th>
                  <th scope="col" className="text-end d-none d-lg-table-cell">Reorder qty</th>
                  <th scope="col" className="text-end d-none d-sm-table-cell">Stock value</th>
                  <th scope="col" className="d-none d-xl-table-cell">Last movement</th>
                  <th scope="col"><span className="visually-hidden">Actions</span></th>
                </tr>
              </thead>
              <tbody>
                {items.map((i) => (
                  <tr key={i.product_id}>
                    <td>
                      <div className="fw-semibold">{i.name}</div>
                      <div className="small text-body-secondary">{i.sku} · {i.category}</div>
                    </td>
                    <td className="text-end fw-semibold">{formatNumber(i.current_stock)}</td>
                    <td><StatusBadge kind="inventory" value={i.inventory_status} /></td>
                    <td className="text-end d-none d-md-table-cell text-nowrap">
                      {formatNumber(i.reorder_point)} / {formatNumber(i.minimum_stock)}
                    </td>
                    <td className="text-end d-none d-lg-table-cell">{formatNumber(i.reorder_quantity)}</td>
                    <td className="text-end d-none d-sm-table-cell">{formatMoney(i.stock_value)}</td>
                    <td className="d-none d-xl-table-cell small text-body-secondary" title={i.last_stock_update ?? ''}>
                      {i.last_stock_update ? formatRelativeTime(i.last_stock_update) : 'Never'}
                    </td>
                    <td className="text-end">
                      <button type="button" className="btn btn-sm btn-outline-primary text-nowrap"
                        onClick={() => onRecord(i.product_id)} aria-label={`Record movement for ${i.name}`}>
                        <i className="bi bi-arrow-left-right" aria-hidden="true" />
                        <span className="d-none d-md-inline ms-1">Movement</span>
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="card-footer small text-body-secondary bg-body d-flex flex-wrap gap-2">
            <span>{formatNumber(items.length)} product{items.length === 1 ? '' : 's'}</span>
            {loading && <span className="spinner-border spinner-border-sm" aria-label="Refreshing" />}
            <span className="ms-auto">
              Thresholds are edited on the <Link to="/products">Products</Link> page.
            </span>
          </div>
        </>
      )}
    </div>
  )
}
