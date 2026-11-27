import { Fragment, useState, type FormEvent } from 'react'
import Modal from '../../components/Modal'
import { recordMovement } from '../../services/inventoryService'
import type { InventoryItem, StockMovementResult, TransactionType } from '../../types/inventory'
import { formatNumber } from '../../utils/format'

interface StockMovementModalProps {
  /** Active products that can receive movements. */
  products: InventoryItem[]
  initialProductId?: number
  onClose: () => void
  onRecorded: (result: StockMovementResult) => void
}

const TYPES: { value: TransactionType; label: string; help: string }[] = [
  { value: 'STOCK_IN', label: 'Stock in', help: 'Goods received (e.g. a supplier delivery).' },
  { value: 'STOCK_OUT', label: 'Stock out', help: 'Goods leaving without a sale (damage, internal use). Sales are recorded separately.' },
  { value: 'RETURN', label: 'Return', help: 'Goods returned by a customer; adds stock.' },
  { value: 'ADJUSTMENT', label: 'Adjustment', help: 'Correction after a stock count, up or down.' },
]

export default function StockMovementModal({ products, initialProductId, onClose, onRecorded }: StockMovementModalProps) {
  const [productId, setProductId] = useState(initialProductId ? String(initialProductId) : '')
  const [type, setType] = useState<TransactionType>('STOCK_IN')
  const [direction, setDirection] = useState<'increase' | 'decrease'>('increase')
  const [quantity, setQuantity] = useState('')
  const [reference, setReference] = useState('')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()

  const product = products.find((p) => String(p.product_id) === productId)
  const typeInfo = TYPES.find((t) => t.value === type)!

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(undefined)
    const amount = Number(quantity)
    try {
      const result = await recordMovement({
        product_id: Number(productId),
        transaction_type: type,
        // The API takes a signed quantity only for adjustments.
        quantity: type === 'ADJUSTMENT' && direction === 'decrease' ? -amount : amount,
        reference: reference.trim() || null,
        notes: notes.trim() || null,
      })
      onRecorded(result)
    } catch (err) {
      setError((err as Error).message)
      setSaving(false)
    }
  }

  const formId = 'movement-form'
  return (
    <Modal
      title="Record stock movement"
      onClose={onClose}
      busy={saving}
      footer={
        <>
          <button type="button" className="btn btn-outline-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" form={formId} className="btn btn-primary" disabled={saving}>
            {saving && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
            Record movement
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
          <label className="form-label" htmlFor="m-product">Product</label>
          <select id="m-product" className="form-select" required value={productId} onChange={(e) => setProductId(e.target.value)}>
            <option value="" disabled>Choose a product…</option>
            {products.map((p) => (
              <option key={p.product_id} value={p.product_id}>
                {p.sku} · {p.name}
              </option>
            ))}
          </select>
          {product && (
            <div className="form-text">
              Current stock: <strong>{formatNumber(product.current_stock)}</strong> · reorder point{' '}
              {formatNumber(product.reorder_point)}
            </div>
          )}
        </div>

        <fieldset className="mb-3">
          <legend className="form-label fs-6">Movement type</legend>
          <div className="btn-group w-100 flex-wrap" role="group">
            {TYPES.map((t) => (
              <Fragment key={t.value}>
                <input type="radio" className="btn-check" name="m-type" id={`m-type-${t.value}`} value={t.value}
                  checked={type === t.value} onChange={() => setType(t.value)} />
                <label className="btn btn-outline-primary" htmlFor={`m-type-${t.value}`}>{t.label}</label>
              </Fragment>
            ))}
          </div>
          <div className="form-text">{typeInfo.help}</div>
        </fieldset>

        <div className="row g-3 mb-3">
          {type === 'ADJUSTMENT' && (
            <div className="col-sm-6">
              <label className="form-label" htmlFor="m-direction">Direction</label>
              <select id="m-direction" className="form-select" value={direction}
                onChange={(e) => setDirection(e.target.value as 'increase' | 'decrease')}>
                <option value="increase">Increase stock</option>
                <option value="decrease">Decrease stock</option>
              </select>
            </div>
          )}
          <div className={type === 'ADJUSTMENT' ? 'col-sm-6' : 'col-12'}>
            <label className="form-label" htmlFor="m-quantity">Quantity (units)</label>
            <input id="m-quantity" className="form-control" type="number" required min="1" max="1000000" step="1"
              value={quantity} onChange={(e) => setQuantity(e.target.value)} />
          </div>
        </div>

        <div className="mb-3">
          <label className="form-label" htmlFor="m-reference">Reference <span className="text-body-secondary">(optional)</span></label>
          <input id="m-reference" className="form-control" maxLength={100} placeholder="e.g. delivery note or PO number"
            value={reference} onChange={(e) => setReference(e.target.value)} />
        </div>
        <div>
          <label className="form-label" htmlFor="m-notes">Notes <span className="text-body-secondary">(optional)</span></label>
          <textarea id="m-notes" className="form-control" rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </div>
      </form>
    </Modal>
  )
}
