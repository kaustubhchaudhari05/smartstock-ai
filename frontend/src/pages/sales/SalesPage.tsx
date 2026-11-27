import { useState } from 'react'
import EmptyState from '../../components/EmptyState'
import ErrorState from '../../components/ErrorState'
import LoadingState from '../../components/LoadingState'
import PageHeader from '../../components/PageHeader'
import StatCard from '../../components/StatCard'
import StatusBadge from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { getSalesAnalytics } from '../../services/salesService'
import type { ProductSalesMetrics, SaleRecorded, SalesTrend } from '../../types/sales'
import { formatDateTime, formatMoney, formatNumber, humanize } from '../../utils/format'
import ProductSalesModal from './ProductSalesModal'
import RecordSaleModal from './RecordSaleModal'

const loadAnalytics = () => getSalesAnalytics()

type SortKey = 'days_remaining' | 'units_sold_30d' | 'units_sold_7d' | 'name'

const SORTS: { value: SortKey; label: string }[] = [
  { value: 'days_remaining', label: 'Fewest days remaining' },
  { value: 'units_sold_30d', label: 'Most sold (30 days)' },
  { value: 'units_sold_7d', label: 'Most sold (7 days)' },
  { value: 'name', label: 'Name' },
]

/** Orders rows by backend-computed values (display ordering only). */
function compare(key: SortKey) {
  return (a: ProductSalesMetrics, b: ProductSalesMetrics): number => {
    switch (key) {
      case 'name':
        return a.name.localeCompare(b.name)
      case 'units_sold_30d':
      case 'units_sold_7d':
        return b[key] - a[key]
      case 'days_remaining': {
        // products without recent sales (null) go last
        if (a.days_remaining === null) return b.days_remaining === null ? 0 : 1
        if (b.days_remaining === null) return -1
        return Number(a.days_remaining) - Number(b.days_remaining)
      }
    }
  }
}

export default function SalesPage() {
  const [refreshKey, setRefreshKey] = useState(0)
  const [trend, setTrend] = useState<'' | SalesTrend>('')
  const [sort, setSort] = useState<SortKey>('days_remaining')
  const [selected, setSelected] = useState<ProductSalesMetrics | null>(null)
  const [saleFor, setSaleFor] = useState<number | 'new' | null>(null)
  const [lastSale, setLastSale] = useState<SaleRecorded>()

  const { data, error, loading, reload } = useApi(loadAnalytics, refreshKey)
  const rows = (data?.products ?? []).filter((p) => !trend || p.trend === trend).sort(compare(sort))
  const s = data?.summary
  const d = data?.definitions

  function recorded(result: SaleRecorded) {
    setSaleFor(null)
    setLastSale(result)
    setRefreshKey((k) => k + 1)
  }

  return (
    <>
      <PageHeader
        title="Sales Analytics"
        subtitle="Demand, trends and how long current stock will last"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setSaleFor('new')} disabled={!data}>
            <i className="bi bi-cart-plus me-1" aria-hidden="true" />
            Record sale
          </button>
        }
      />

      {lastSale && (
        <div className="alert alert-success alert-dismissible" role="status">
          <i className="bi bi-check-circle me-2" aria-hidden="true" />
          Sale recorded: <strong>{lastSale.sale.product_name}</strong> × {formatNumber(lastSale.sale.quantity_sold)} for{' '}
          {formatMoney(lastSale.sale.total_amount)}. Stock {formatNumber(lastSale.previous_stock)} →{' '}
          <strong>{formatNumber(lastSale.current_stock)}</strong>.
          <button type="button" className="btn-close" aria-label="Dismiss" onClick={() => setLastSale(undefined)} />
        </div>
      )}

      {error && (
        <div className="mb-3">
          <ErrorState error={error} onRetry={reload} />
        </div>
      )}
      {!data && loading && <LoadingState label="Loading sales analytics…" />}

      {s && d && (
        <>
          <div className="row g-3 mb-3">
            <div className="col-12 col-sm-6 col-xl-3">
              <StatCard label={`Units sold, last ${d.short_window_days} days`} icon="calendar-week"
                value={formatNumber(s.units_sold_7d)} />
            </div>
            <div className="col-12 col-sm-6 col-xl-3">
              <StatCard label={`Units sold, last ${d.long_window_days} days`} icon="calendar3"
                value={formatNumber(s.units_sold_30d)} />
            </div>
            <div className="col-12 col-xl-6">
              <div className="card h-100">
                <div className="card-body">
                  <div className="text-body-secondary small mb-2">Demand trend ({formatNumber(s.products)} products)</div>
                  <div className="d-flex flex-wrap gap-3">
                    {([
                      ['INCREASING', s.increasing],
                      ['STABLE', s.stable],
                      ['DECREASING', s.decreasing],
                      ['INSUFFICIENT_DATA', s.insufficient_data],
                    ] as [SalesTrend, number][]).map(([t, count]) => (
                      <button key={t} type="button"
                        className={`btn btn-sm ${trend === t ? 'btn-primary' : 'btn-outline-secondary'}`}
                        aria-pressed={trend === t} onClick={() => setTrend(trend === t ? '' : t)}>
                        <span className="fw-semibold">{formatNumber(count)}</span> {humanize(t)}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <p className="small text-body-secondary">
            <i className="bi bi-info-circle me-1" aria-hidden="true" />
            Rolling windows ending {formatDateTime(data.as_of)}. Average daily demand = units sold in the last{' '}
            {d.long_window_days} days ÷ {d.long_window_days}. Trend compares the {d.short_window_days}-day and{' '}
            {d.long_window_days}-day daily averages (±{Math.round(Number(d.trend_threshold) * 100)}%).
          </p>
        </>
      )}

      {data && (
        <div className="card">
          <div className="card-body border-bottom d-flex flex-wrap align-items-center gap-2">
            <label htmlFor="sales-sort" className="small text-body-secondary mb-0">Sort by</label>
            <select id="sales-sort" className="form-select form-select-sm w-auto" value={sort}
              onChange={(e) => setSort(e.target.value as SortKey)}>
              {SORTS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            {trend && (
              <button type="button" className="btn btn-sm btn-link" onClick={() => setTrend('')}>
                Clear trend filter
              </button>
            )}
          </div>
          {rows.length === 0 ? (
            <EmptyState icon="graph-up" title="No products with this trend" />
          ) : (
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead>
                  <tr>
                    <th scope="col">Product</th>
                    <th scope="col" className="text-end">Stock</th>
                    <th scope="col" className="text-end">Days left</th>
                    <th scope="col" className="text-end d-none d-md-table-cell">Avg / day</th>
                    <th scope="col" className="text-end d-none d-sm-table-cell">7 days</th>
                    <th scope="col" className="text-end d-none d-sm-table-cell">30 days</th>
                    <th scope="col">Trend</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((p) => (
                    <tr key={p.product_id}>
                      <td>
                        <button type="button" className="btn btn-link p-0 text-start text-decoration-none fw-semibold"
                          onClick={() => setSelected(p)}>
                          {p.name}
                        </button>
                        <div className="small text-body-secondary">{p.sku}</div>
                      </td>
                      <td className="text-end tabular-nums">{formatNumber(p.current_stock)}</td>
                      <td className="text-end tabular-nums fw-semibold">
                        {p.days_remaining ?? <span className="text-body-secondary fw-normal">—</span>}
                      </td>
                      <td className="text-end tabular-nums d-none d-md-table-cell">{p.average_daily_sales}</td>
                      <td className="text-end tabular-nums d-none d-sm-table-cell">{formatNumber(p.units_sold_7d)}</td>
                      <td className="text-end tabular-nums d-none d-sm-table-cell">{formatNumber(p.units_sold_30d)}</td>
                      <td><StatusBadge kind="trend" value={p.trend} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="card-footer small text-body-secondary bg-body">
            {formatNumber(rows.length)} product{rows.length === 1 ? '' : 's'} · days left = current stock ÷ average daily
            demand, from the backend
            {loading && <span className="spinner-border spinner-border-sm ms-2" aria-label="Refreshing" />}
          </div>
        </div>
      )}

      {selected && (
        <ProductSalesModal
          productId={selected.product_id}
          title={`${selected.name} · ${selected.sku}`}
          refreshKey={refreshKey}
          onClose={() => setSelected(null)}
          onRecordSale={() => {
            setSaleFor(selected.product_id)
            setSelected(null)
          }}
        />
      )}
      {saleFor !== null && data && (
        <RecordSaleModal
          products={data.products}
          initialProductId={saleFor === 'new' ? undefined : saleFor}
          onClose={() => setSaleFor(null)}
          onRecorded={recorded}
        />
      )}
    </>
  )
}
