import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import PageHeader from '../../components/PageHeader'
import { useApi } from '../../hooks/useApi'
import { getInventoryOverview } from '../../services/inventoryService'
import type { StockMovementResult } from '../../types/inventory'
import { formatNumber, humanize } from '../../utils/format'
import CurrentStockTab from './CurrentStockTab'
import MovementHistoryTab from './MovementHistoryTab'
import StockMovementModal from './StockMovementModal'

type Tab = 'stock' | 'history'

// All active products (for the movement form, history filter and category list).
const loadAllInventory = () => getInventoryOverview()

export default function InventoryPage() {
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'history' ? 'history' : 'stock'
  const [refreshKey, setRefreshKey] = useState(0)
  const [movementFor, setMovementFor] = useState<number | 'new' | null>(null)
  const [lastResult, setLastResult] = useState<StockMovementResult>()

  const all = useApi(loadAllInventory, refreshKey)
  const products = all.data?.items ?? []
  const categories = useMemo(() => (all.data?.categories ?? []).map((c) => c.category), [all.data])

  function recorded(result: StockMovementResult) {
    setMovementFor(null)
    setLastResult(result)
    setRefreshKey((k) => k + 1)
  }

  const t = lastResult?.transaction
  return (
    <>
      <PageHeader
        title="Inventory"
        subtitle="Current stock, thresholds and every stock movement"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setMovementFor('new')} disabled={!all.data}>
            <i className="bi bi-arrow-left-right me-1" aria-hidden="true" />
            Record movement
          </button>
        }
      />

      {lastResult && t && (
        <div className="alert alert-success alert-dismissible" role="status">
          <i className="bi bi-check-circle me-2" aria-hidden="true" />
          <strong>{t.product_name}</strong> ({t.product_sku}): {humanize(t.transaction_type).toLowerCase()}{' '}
          {t.stock_change > 0 ? '+' : ''}{formatNumber(t.stock_change)}. Stock{' '}
          {formatNumber(lastResult.previous_stock)} → <strong>{formatNumber(lastResult.current_stock)}</strong>.
          <button type="button" className="btn-close" aria-label="Dismiss" onClick={() => setLastResult(undefined)} />
        </div>
      )}

      <ul className="nav nav-tabs mb-3">
        <li className="nav-item">
          <button type="button" className={`nav-link ${tab === 'stock' ? 'active' : ''}`}
            aria-current={tab === 'stock' ? 'page' : undefined} onClick={() => setParams({})}>
            <i className="bi bi-boxes me-1" aria-hidden="true" />
            Current stock
          </button>
        </li>
        <li className="nav-item">
          <button type="button" className={`nav-link ${tab === 'history' ? 'active' : ''}`}
            aria-current={tab === 'history' ? 'page' : undefined} onClick={() => setParams({ tab: 'history' })}>
            <i className="bi bi-clock-history me-1" aria-hidden="true" />
            Movement history
          </button>
        </li>
      </ul>

      {tab === 'stock' ? (
        <CurrentStockTab categories={categories} refreshKey={refreshKey} onRecord={(id) => setMovementFor(id)} />
      ) : (
        <MovementHistoryTab products={products} refreshKey={refreshKey} />
      )}

      {movementFor !== null && (
        <StockMovementModal
          products={products}
          initialProductId={movementFor === 'new' ? undefined : movementFor}
          onClose={() => setMovementFor(null)}
          onRecorded={recorded}
        />
      )}
    </>
  )
}
