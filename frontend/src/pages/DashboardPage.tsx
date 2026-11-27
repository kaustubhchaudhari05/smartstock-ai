import type { ReactNode } from 'react'
import { Link } from 'react-router'
import EmptyState from '../components/EmptyState'
import ErrorState from '../components/ErrorState'
import LoadingState from '../components/LoadingState'
import PageHeader from '../components/PageHeader'
import StatCard from '../components/StatCard'
import StatusBadge from '../components/StatusBadge'
import { useApi } from '../hooks/useApi'
import { listAlerts } from '../services/alertService'
import { getInventoryOverview } from '../services/inventoryService'
import { getPurchaseOrderSummary } from '../services/purchaseOrderService'
import { listRecommendations } from '../services/recommendationService'
import { formatMoney, formatNumber, formatRelativeTime } from '../utils/format'

const RECENT_LIMIT = 5

// Stable loaders (see useApi). Every number shown is computed by the backend.
const loadInventory = () => getInventoryOverview()
const loadOrderSummary = () => getPurchaseOrderSummary()
const loadAlerts = () => listAlerts({ unresolved_only: true, limit: RECENT_LIMIT })
const loadRecommendations = () => listRecommendations({ limit: RECENT_LIMIT })

interface PanelProps {
  title: string
  to: string
  linkLabel: string
  children: ReactNode
}

function Panel({ title, to, linkLabel, children }: PanelProps) {
  return (
    <div className="card h-100">
      <div className="card-header d-flex align-items-center justify-content-between bg-body">
        <h2 className="h6 mb-0">{title}</h2>
        <Link to={to} className="small">
          {linkLabel} <i className="bi bi-arrow-right" aria-hidden="true" />
        </Link>
      </div>
      {children}
    </div>
  )
}

const loadingValue = <span className="placeholder col-6 rounded" aria-label="Loading" />

function Stats() {
  const inventory = useApi(loadInventory)
  const orders = useApi(loadOrderSummary)
  const s = inventory.data?.summary
  const o = orders.data

  return (
    <>
      {inventory.error && (
        <div className="mb-3">
          <ErrorState error={inventory.error} onRetry={inventory.reload} />
        </div>
      )}
      {orders.error && (
        <div className="mb-3">
          <ErrorState error={orders.error} onRetry={orders.reload} />
        </div>
      )}
      <div className="row g-3 mb-4 placeholder-glow">
        <div className="col-12 col-sm-6 col-xl">
          <StatCard
            label="Total products"
            icon="box-seam"
            to="/products"
            value={s ? formatNumber(s.total_products) : loadingValue}
            hint={s && `${formatNumber(s.total_units)} units in stock`}
          />
        </div>
        <div className="col-12 col-sm-6 col-xl">
          <StatCard
            label="Inventory value"
            icon="currency-rupee"
            color="success"
            to="/inventory"
            value={s ? formatMoney(s.total_stock_value) : loadingValue}
            hint={s && 'At unit cost'}
          />
        </div>
        <div className="col-12 col-sm-6 col-xl">
          <StatCard
            label="Low stock"
            icon="exclamation-triangle"
            color="warning"
            to="/inventory"
            value={s ? formatNumber(s.low_stock_count) : loadingValue}
            hint={
              s &&
              `${formatNumber(s.reorder_needed_count)} need reorder · ${formatMoney(s.replenishment_cost)}`
            }
          />
        </div>
        <div className="col-12 col-sm-6 col-xl">
          <StatCard
            label="Out of stock"
            icon="x-octagon"
            color="danger"
            to="/inventory"
            value={s ? formatNumber(s.out_of_stock_count) : loadingValue}
            hint={s && (s.out_of_stock_count > 0 ? 'Cannot be sold now' : 'Everything is available')}
          />
        </div>
        <div className="col-12 col-sm-6 col-xl">
          <StatCard
            label="Pending purchase orders"
            icon="receipt"
            color="info"
            to="/purchase-orders"
            value={o ? formatNumber(o.awaiting_decision_count) : loadingValue}
            hint={o && `${formatMoney(o.awaiting_decision_amount)} awaiting approval`}
          />
        </div>
      </div>
    </>
  )
}

function RecentAlerts() {
  const { data, error, loading, reload } = useApi(loadAlerts)
  return (
    <Panel title="Recent inventory alerts" to="/alerts" linkLabel="All alerts">
      {loading && <LoadingState />}
      {error && (
        <div className="card-body">
          <ErrorState error={error} onRetry={reload} />
        </div>
      )}
      {data && data.length === 0 && (
        <EmptyState icon="check-circle" title="No open alerts" message="Every product is above its reorder point." />
      )}
      {data && data.length > 0 && (
        <ul className="list-group list-group-flush">
          {data.map((alert) => (
            <li key={alert.id} className="list-group-item">
              <div className="d-flex flex-wrap align-items-center gap-2 mb-1">
                <StatusBadge kind="severity" value={alert.severity} />
                <span className="fw-semibold">{alert.product_name}</span>
                <span className="text-body-secondary small">{alert.product_sku}</span>
                {alert.status === 'ACKNOWLEDGED' && <StatusBadge kind="alertStatus" value={alert.status} />}
                <span className="ms-auto small text-body-secondary" title={alert.created_at}>
                  {formatRelativeTime(alert.created_at)}
                </span>
              </div>
              <div className="small text-body-secondary">{alert.message}</div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function RecentRecommendations() {
  const { data, error, loading, reload } = useApi(loadRecommendations)
  return (
    <Panel title="AI recommendations" to="/ai-insights" linkLabel="AI Insights">
      {loading && <LoadingState />}
      {error && (
        <div className="card-body">
          <ErrorState error={error} onRetry={reload} />
        </div>
      )}
      {data && data.length === 0 && (
        <EmptyState
          icon="stars"
          title="No recommendations yet"
          message="Generate one for a low-stock product on the AI Insights page."
        />
      )}
      {data && data.length > 0 && (
        <ul className="list-group list-group-flush">
          {data.map((rec) => (
            <li key={rec.id} className="list-group-item">
              <div className="d-flex flex-wrap align-items-center gap-2 mb-1">
                <StatusBadge kind="risk" value={rec.risk_level} prefix="Risk" />
                <span className="fw-semibold">{rec.product_name}</span>
                <span className="text-body-secondary small">{rec.product_sku}</span>
                <span className="ms-auto small text-body-secondary" title={rec.created_at}>
                  {formatRelativeTime(rec.created_at)}
                </span>
              </div>
              <div className="small mb-2">{rec.recommendation}</div>
              <div className="d-flex flex-wrap align-items-center gap-2 small">
                <StatusBadge kind="urgency" value={rec.urgency} />
                <span className="text-body-secondary">
                  Suggested <strong className="text-body">{formatNumber(rec.suggested_quantity)}</strong> units
                </span>
                <StatusBadge kind="recommendationStatus" value={rec.status} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

export default function DashboardPage() {
  return (
    <>
      <PageHeader title="Dashboard" subtitle="Stock overview, alerts and pending decisions" />
      <Stats />
      <div className="row g-3">
        <div className="col-12 col-lg-6">
          <RecentAlerts />
        </div>
        <div className="col-12 col-lg-6">
          <RecentRecommendations />
        </div>
      </div>
    </>
  )
}
