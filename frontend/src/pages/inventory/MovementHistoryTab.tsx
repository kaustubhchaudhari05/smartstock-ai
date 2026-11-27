import { useCallback, useState } from 'react'
import EmptyState from '../../components/EmptyState'
import ErrorState from '../../components/ErrorState'
import LoadingState from '../../components/LoadingState'
import StatusBadge from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { listTransactions } from '../../services/inventoryService'
import type { InventoryItem, TransactionType } from '../../types/inventory'
import { formatDateTime, formatNumber, humanize } from '../../utils/format'

interface MovementHistoryTabProps {
  products: InventoryItem[]
  refreshKey: number
}

const PAGE_SIZE = 25
const TYPES: TransactionType[] = ['STOCK_IN', 'STOCK_OUT', 'ADJUSTMENT', 'RETURN']

/** "2026-11-27" (local date) -> ISO timestamp of local midnight, optionally a day later. */
function localDayStart(date: string, addDays = 0): string {
  const d = new Date(`${date}T00:00:00`)
  d.setDate(d.getDate() + addDays)
  return d.toISOString()
}

export default function MovementHistoryTab({ products, refreshKey }: MovementHistoryTabProps) {
  const [productId, setProductId] = useState('')
  const [type, setType] = useState<'' | TransactionType>('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(0)

  // Filtering and paging are done by the backend. "To" is inclusive for the user, so the
  // exclusive date_to sent is the start of the following day.
  const load = useCallback(
    () =>
      listTransactions({
        product_id: productId ? Number(productId) : undefined,
        transaction_type: type || undefined,
        date_from: from ? localDayStart(from) : undefined,
        date_to: to ? localDayStart(to, 1) : undefined,
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
      }),
    [productId, type, from, to, page],
  )
  const { data, error, loading, reload } = useApi(load, refreshKey)
  const filtered = Boolean(productId || type || from || to)

  // Any filter change goes back to the first page.
  const filter = <T,>(setter: (v: T) => void) => (value: T) => {
    setter(value)
    setPage(0)
  }

  return (
    <div className="card">
      <div className="card-body border-bottom">
        <div className="row g-2">
          <div className="col-12 col-md-4">
            <select className="form-select" aria-label="Product" value={productId}
              onChange={(e) => filter(setProductId)(e.target.value)}>
              <option value="">All products</option>
              {products.map((p) => (
                <option key={p.product_id} value={p.product_id}>{p.sku} · {p.name}</option>
              ))}
            </select>
          </div>
          <div className="col-12 col-sm-4 col-md-2">
            <select className="form-select" aria-label="Movement type" value={type}
              onChange={(e) => filter(setType)(e.target.value as '' | TransactionType)}>
              <option value="">All types</option>
              {TYPES.map((t) => (
                <option key={t} value={t}>{humanize(t)}</option>
              ))}
            </select>
          </div>
          <div className="col-6 col-sm-4 col-md-3">
            <div className="input-group">
              <span className="input-group-text">From</span>
              <input type="date" className="form-control" aria-label="From date" value={from} max={to || undefined}
                onChange={(e) => filter(setFrom)(e.target.value)} />
            </div>
          </div>
          <div className="col-6 col-sm-4 col-md-3">
            <div className="input-group">
              <span className="input-group-text">To</span>
              <input type="date" className="form-control" aria-label="To date" value={to} min={from || undefined}
                onChange={(e) => filter(setTo)(e.target.value)} />
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div className="card-body">
          <ErrorState error={error} onRetry={reload} />
        </div>
      )}
      {!data && loading && <LoadingState label="Loading movements…" />}
      {data && data.length === 0 && (
        <EmptyState icon="clock-history" title={page > 0 ? 'No more movements' : 'No movements found'}
          message={filtered ? 'Try other filters.' : 'Stock movements will appear here.'} />
      )}
      {data && data.length > 0 && (
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0">
            <thead>
              <tr>
                <th scope="col">When</th>
                <th scope="col">Product</th>
                <th scope="col">Type</th>
                <th scope="col" className="text-end">Change</th>
                <th scope="col" className="d-none d-md-table-cell">Reference</th>
                <th scope="col" className="d-none d-lg-table-cell">Notes</th>
              </tr>
            </thead>
            <tbody>
              {data.map((t) => (
                <tr key={t.id}>
                  <td className="small text-nowrap">{formatDateTime(t.created_at)}</td>
                  <td>
                    <div className="fw-semibold">{t.product_name}</div>
                    <div className="small text-body-secondary">{t.product_sku}</div>
                  </td>
                  <td><StatusBadge kind="transactionType" value={t.transaction_type} /></td>
                  <td className={`text-end fw-semibold ${t.stock_change < 0 ? 'text-danger' : 'text-success'}`}>
                    {t.stock_change > 0 ? '+' : ''}{formatNumber(t.stock_change)}
                  </td>
                  <td className="d-none d-md-table-cell small">{t.reference ?? <span className="text-body-secondary">—</span>}</td>
                  <td className="d-none d-lg-table-cell small text-body-secondary">{t.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data && (page > 0 || data.length === PAGE_SIZE) && (
        <div className="card-footer bg-body d-flex align-items-center gap-2">
          <button type="button" className="btn btn-sm btn-outline-secondary" disabled={page === 0 || loading}
            onClick={() => setPage((p) => p - 1)}>
            <i className="bi bi-chevron-left" aria-hidden="true" /> Newer
          </button>
          <span className="small text-body-secondary">Page {page + 1}</span>
          <button type="button" className="btn btn-sm btn-outline-secondary" disabled={data.length < PAGE_SIZE || loading}
            onClick={() => setPage((p) => p + 1)}>
            Older <i className="bi bi-chevron-right" aria-hidden="true" />
          </button>
          {loading && <span className="spinner-border spinner-border-sm" aria-label="Refreshing" />}
        </div>
      )}
    </div>
  )
}
