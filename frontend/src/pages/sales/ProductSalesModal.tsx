import { useCallback, type ReactNode } from 'react'
import DailySalesChart from '../../components/DailySalesChart'
import ErrorState from '../../components/ErrorState'
import LoadingState from '../../components/LoadingState'
import Modal from '../../components/Modal'
import StatusBadge from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { getSalesAnalytics, listSales } from '../../services/salesService'
import { formatDateTime, formatMoney, formatNumber } from '../../utils/format'

interface ProductSalesModalProps {
  productId: number
  title: string
  refreshKey: number
  onClose: () => void
  onRecordSale: () => void
}

function Metric({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="col-6 col-md-3">
      <div className="small text-body-secondary">{label}</div>
      <div className="fw-semibold">{children}</div>
    </div>
  )
}

export default function ProductSalesModal({ productId, title, refreshKey, onClose, onRecordSale }: ProductSalesModalProps) {
  const loadMetrics = useCallback(() => getSalesAnalytics({ product_id: productId }), [productId])
  const loadSales = useCallback(() => listSales({ product_id: productId, limit: 10 }), [productId])
  const analytics = useApi(loadMetrics, refreshKey)
  const sales = useApi(loadSales, refreshKey)
  const m = analytics.data?.products[0]

  return (
    <Modal
      title={title}
      onClose={onClose}
      size="lg"
      footer={
        <button type="button" className="btn btn-primary" onClick={onRecordSale}>
          <i className="bi bi-cart-plus me-1" aria-hidden="true" />
          Record sale
        </button>
      }
    >
      {analytics.error && <ErrorState error={analytics.error} onRetry={analytics.reload} />}
      {!m && analytics.loading && <LoadingState />}
      {m && (
        <>
          <div className="row g-3 mb-3">
            <Metric label="Current stock">{formatNumber(m.current_stock)} units</Metric>
            <Metric label="Days remaining">{m.days_remaining ?? 'No recent sales'}</Metric>
            <Metric label="Avg / day (30 days)">{m.average_daily_sales}</Metric>
            <Metric label="Trend"><StatusBadge kind="trend" value={m.trend} /></Metric>
            <Metric label="Last 7 days">{formatNumber(m.units_sold_7d)} units · {m.average_daily_sales_7d}/day</Metric>
            <Metric label="Last 30 days">{formatNumber(m.units_sold_30d)} units</Metric>
            <Metric label="All time">{formatNumber(m.units_sold_total)} units</Metric>
          </div>
          <h3 className="h6">Units sold per day, last 30 days</h3>
          {m.daily_sales && <DailySalesChart data={m.daily_sales} label={`${m.name}: units sold per day, last 30 days`} />}
        </>
      )}

      <h3 className="h6 mt-4">Recent sales</h3>
      {sales.error && <ErrorState error={sales.error} onRetry={sales.reload} />}
      {sales.data && sales.data.length === 0 && <p className="text-body-secondary small mb-0">No sales recorded.</p>}
      {sales.data && sales.data.length > 0 && (
        <div className="table-responsive">
          <table className="table table-sm align-middle mb-0">
            <thead>
              <tr>
                <th scope="col">Date</th>
                <th scope="col" className="text-end">Qty</th>
                <th scope="col" className="text-end">Unit price</th>
                <th scope="col" className="text-end">Total</th>
                <th scope="col" className="d-none d-sm-table-cell">Reference</th>
              </tr>
            </thead>
            <tbody>
              {sales.data.map((s) => (
                <tr key={s.id}>
                  <td className="small">{formatDateTime(s.sale_date)}</td>
                  <td className="text-end tabular-nums">{formatNumber(s.quantity_sold)}</td>
                  <td className="text-end tabular-nums">{formatMoney(s.unit_price)}</td>
                  <td className="text-end tabular-nums">{formatMoney(s.total_amount)}</td>
                  <td className="d-none d-sm-table-cell small text-body-secondary">{s.reference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  )
}
