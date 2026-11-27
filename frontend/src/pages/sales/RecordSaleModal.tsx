import { useEffect, useState, type FormEvent } from 'react'
import Modal from '../../components/Modal'
import { listSales, recordSale } from '../../services/salesService'
import type { ProductSalesMetrics, SaleRecorded } from '../../types/sales'
import { formatNumber } from '../../utils/format'

interface RecordSaleModalProps {
  products: ProductSalesMetrics[]
  initialProductId?: number
  onClose: () => void
  onRecorded: (result: SaleRecorded) => void
}

export default function RecordSaleModal({ products, initialProductId, onClose, onRecorded }: RecordSaleModalProps) {
  const [productId, setProductId] = useState(initialProductId ? String(initialProductId) : '')
  const [quantity, setQuantity] = useState('')
  const [unitPrice, setUnitPrice] = useState('')
  const [reference, setReference] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()
  const product = products.find((p) => String(p.product_id) === productId)

  // Products have no list price: suggest the price of the product's latest sale.
  useEffect(() => {
    if (!productId) return
    let cancelled = false
    listSales({ product_id: Number(productId), limit: 1 })
      .then((latest) => {
        if (!cancelled && latest[0]) setUnitPrice(latest[0].unit_price)
      })
      .catch(() => undefined) // the suggestion is optional
    return () => {
      cancelled = true
    }
  }, [productId])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(undefined)
    try {
      onRecorded(
        await recordSale({
          product_id: Number(productId),
          quantity_sold: Number(quantity),
          unit_price: unitPrice.trim(),
          reference: reference.trim() || null,
        }),
      )
    } catch (err) {
      setError((err as Error).message)
      setSaving(false)
    }
  }

  const formId = 'sale-form'
  return (
    <Modal
      title="Record sale"
      onClose={onClose}
      busy={saving}
      footer={
        <>
          <button type="button" className="btn btn-outline-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" form={formId} className="btn btn-primary" disabled={saving}>
            {saving && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
            Record sale
          </button>
        </>
      }
    >
      <form id={formId} onSubmit={submit}>
        {error && (
          <div className="alert alert-danger" role="alert">
            {error}
          </div>
        )}
        <div className="mb-3">
          <label className="form-label" htmlFor="s-product">Product</label>
          <select id="s-product" className="form-select" required value={productId}
            onChange={(e) => {
              setProductId(e.target.value)
              setUnitPrice('')
            }}>
            <option value="" disabled>Choose a product…</option>
            {products.map((p) => (
              <option key={p.product_id} value={p.product_id}>{p.sku} · {p.name}</option>
            ))}
          </select>
          {product && <div className="form-text">In stock: <strong>{formatNumber(product.current_stock)}</strong></div>}
        </div>
        <div className="row g-3 mb-3">
          <div className="col-sm-6">
            <label className="form-label" htmlFor="s-qty">Quantity sold</label>
            <input id="s-qty" className="form-control" type="number" required min="1" max="1000000" step="1"
              value={quantity} onChange={(e) => setQuantity(e.target.value)} />
          </div>
          <div className="col-sm-6">
            <label className="form-label" htmlFor="s-price">Unit price (₹)</label>
            <input id="s-price" className="form-control" type="number" required min="0" step="0.01" inputMode="decimal"
              value={unitPrice} onChange={(e) => setUnitPrice(e.target.value)} aria-describedby="s-price-help" />
            <div id="s-price-help" className="form-text">Pre-filled with the latest sale price.</div>
          </div>
        </div>
        <div>
          <label className="form-label" htmlFor="s-ref">Reference <span className="text-body-secondary">(optional)</span></label>
          <input id="s-ref" className="form-control" maxLength={100} placeholder="e.g. order or invoice number"
            value={reference} onChange={(e) => setReference(e.target.value)} />
        </div>
        <p className="small text-body-secondary mt-3 mb-0">
          Stock is reduced in the same step. If stock falls to the reorder point, a low-stock alert is raised automatically.
        </p>
      </form>
    </Modal>
  )
}
