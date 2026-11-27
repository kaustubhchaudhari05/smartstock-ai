import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import Modal from '../../components/Modal'
import StatusBadge from '../../components/StatusBadge'
import { deactivateProduct, reactivateProduct } from '../../services/productService'
import type { Product } from '../../types/product'
import { formatDateTime, formatMoney, formatNumber } from '../../utils/format'

interface ProductDetailModalProps {
  product: Product
  onClose: () => void
  onEdit: () => void
  onChanged: (product: Product) => void
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="col-6 col-md-4">
      <div className="small text-body-secondary">{label}</div>
      <div className="fw-semibold">{children}</div>
    </div>
  )
}

export default function ProductDetailModal({ product, onClose, onEdit, onChanged }: ProductDetailModalProps) {
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string>()

  async function toggleActive() {
    setBusy(true)
    setError(undefined)
    try {
      onChanged(product.is_active ? await deactivateProduct(product.id) : await reactivateProduct(product.id))
      setConfirming(false)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      title={
        <>
          {product.name} <span className="text-body-secondary fw-normal">{product.sku}</span>
        </>
      }
      onClose={onClose}
      busy={busy}
      size="lg"
      footer={
        confirming ? (
          <>
            <span className="me-auto small">Deactivate {product.sku}? It disappears from lists and its alerts are resolved.</span>
            <button type="button" className="btn btn-outline-secondary" onClick={() => setConfirming(false)} disabled={busy}>
              Keep active
            </button>
            <button type="button" className="btn btn-danger" onClick={toggleActive} disabled={busy}>
              Deactivate
            </button>
          </>
        ) : (
          <>
            {product.is_active ? (
              <button type="button" className="btn btn-outline-danger me-auto" onClick={() => setConfirming(true)}>
                <i className="bi bi-archive me-1" aria-hidden="true" />
                Deactivate
              </button>
            ) : (
              <button type="button" className="btn btn-outline-success me-auto" onClick={toggleActive} disabled={busy}>
                <i className="bi bi-arrow-counterclockwise me-1" aria-hidden="true" />
                Reactivate
              </button>
            )}
            <button type="button" className="btn btn-primary" onClick={onEdit}>
              <i className="bi bi-pencil me-1" aria-hidden="true" />
              Edit
            </button>
          </>
        )
      }
    >
      {error && (
        <div className="alert alert-danger" role="alert">
          {error}
        </div>
      )}
      <div className="d-flex flex-wrap gap-2 mb-3">
        <StatusBadge kind="inventory" value={product.inventory_status} />
        <span className="badge text-bg-light border">{product.category}</span>
        {!product.is_active && <span className="badge text-bg-dark">Inactive</span>}
      </div>
      {product.description && <p className="text-body-secondary">{product.description}</p>}
      <div className="row g-3">
        <Field label="Current stock">{formatNumber(product.current_stock)} units</Field>
        <Field label="Reorder point">{formatNumber(product.reorder_point)}</Field>
        <Field label="Minimum stock">{formatNumber(product.minimum_stock)}</Field>
        <Field label="Reorder quantity">{formatNumber(product.reorder_quantity)}</Field>
        <Field label="Unit cost">{formatMoney(product.unit_cost)}</Field>
        <Field label="Supplier">{product.supplier?.name ?? <span className="text-body-secondary">None</span>}</Field>
        <Field label="Created">{formatDateTime(product.created_at)}</Field>
        <Field label="Last updated">{formatDateTime(product.updated_at)}</Field>
      </div>
      <hr />
      <Link to="/inventory" className="small">
        <i className="bi bi-boxes me-1" aria-hidden="true" />
        Record a stock movement on the Inventory page
      </Link>
    </Modal>
  )
}
