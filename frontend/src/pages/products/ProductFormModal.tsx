import { useState, type FormEvent } from 'react'
import Modal from '../../components/Modal'
import { createProduct, updateProduct } from '../../services/productService'
import type { Product, ProductCreate, ProductUpdate } from '../../types/product'
import type { Supplier } from '../../types/supplier'

interface ProductFormModalProps {
  /** Product to edit; omit to create a new one. */
  product?: Product
  suppliers: Supplier[]
  categories: string[]
  onClose: () => void
  onSaved: (product: Product) => void
}

/** Form values are kept as strings exactly as typed; the backend validates them. */
interface FormValues {
  sku: string
  name: string
  category: string
  description: string
  supplier_id: string
  unit_cost: string
  current_stock: string
  reorder_point: string
  minimum_stock: string
  reorder_quantity: string
}

function initialValues(product?: Product): FormValues {
  return {
    sku: product?.sku ?? '',
    name: product?.name ?? '',
    category: product?.category ?? '',
    description: product?.description ?? '',
    supplier_id: product?.supplier_id ? String(product.supplier_id) : '',
    unit_cost: product?.unit_cost ?? '',
    current_stock: product ? String(product.current_stock) : '0',
    reorder_point: product ? String(product.reorder_point) : '',
    minimum_stock: product ? String(product.minimum_stock) : '',
    reorder_quantity: product ? String(product.reorder_quantity) : '',
  }
}

function toPayload(v: FormValues): ProductCreate {
  return {
    sku: v.sku.trim(),
    name: v.name.trim(),
    category: v.category.trim(),
    description: v.description.trim() || null,
    supplier_id: v.supplier_id ? Number(v.supplier_id) : null,
    unit_cost: v.unit_cost.trim(),
    current_stock: Number(v.current_stock),
    reorder_point: Number(v.reorder_point),
    minimum_stock: Number(v.minimum_stock),
    reorder_quantity: Number(v.reorder_quantity),
  }
}

/** Only the fields that differ from the saved product (PUT is a partial update). */
function changedFields(product: Product, payload: ProductCreate): ProductUpdate {
  const changes: ProductUpdate = {}
  const original = toPayload(initialValues(product))
  for (const key of Object.keys(payload) as (keyof ProductCreate)[]) {
    if (key === 'current_stock') continue // stock changes go through inventory movements
    const before = key === 'unit_cost' ? Number(original[key]) : original[key]
    const after = key === 'unit_cost' ? Number(payload[key]) : payload[key]
    if (before !== after) Object.assign(changes, { [key]: payload[key] })
  }
  return changes
}

export default function ProductFormModal({ product, suppliers, categories, onClose, onSaved }: ProductFormModalProps) {
  const [values, setValues] = useState<FormValues>(() => initialValues(product))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string>()
  const editing = product !== undefined

  // Active suppliers can be assigned; keep the current one listed even if it was deactivated.
  const supplierOptions = suppliers.filter((s) => s.is_active || s.id === product?.supplier_id)

  const set = (field: keyof FormValues) => (e: { target: { value: string } }) =>
    setValues((v) => ({ ...v, [field]: e.target.value }))

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(undefined)
    try {
      const payload = toPayload(values)
      if (editing) {
        const changes = changedFields(product, payload)
        onSaved(Object.keys(changes).length ? await updateProduct(product.id, changes) : product)
      } else {
        onSaved(await createProduct(payload))
      }
    } catch (err) {
      setError((err as Error).message)
      setSaving(false)
    }
  }

  const formId = 'product-form'
  return (
    <Modal
      title={editing ? `Edit ${product.sku}` : 'New product'}
      onClose={onClose}
      busy={saving}
      size="lg"
      footer={
        <>
          <button type="button" className="btn btn-outline-secondary" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button type="submit" form={formId} className="btn btn-primary" disabled={saving}>
            {saving && <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />}
            {editing ? 'Save changes' : 'Create product'}
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
        <div className="row g-3">
          <div className="col-sm-4">
            <label className="form-label" htmlFor="p-sku">SKU</label>
            <input id="p-sku" className="form-control text-uppercase" required maxLength={64}
              pattern="[A-Za-z0-9][A-Za-z0-9._\-]*" title="Letters, digits, dot, dash or underscore"
              value={values.sku} onChange={set('sku')} />
          </div>
          <div className="col-sm-8">
            <label className="form-label" htmlFor="p-name">Name</label>
            <input id="p-name" className="form-control" required maxLength={255}
              value={values.name} onChange={set('name')} />
          </div>
          <div className="col-sm-6">
            <label className="form-label" htmlFor="p-category">Category</label>
            <input id="p-category" className="form-control" required maxLength={100} list="p-categories"
              value={values.category} onChange={set('category')} />
            <datalist id="p-categories">
              {categories.map((c) => <option key={c} value={c} />)}
            </datalist>
          </div>
          <div className="col-sm-6">
            <label className="form-label" htmlFor="p-supplier">Supplier</label>
            <select id="p-supplier" className="form-select" value={values.supplier_id} onChange={set('supplier_id')}>
              <option value="">No supplier</option>
              {supplierOptions.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}{s.is_active ? '' : ' (inactive)'}
                </option>
              ))}
            </select>
          </div>
          <div className="col-12">
            <label className="form-label" htmlFor="p-description">Description <span className="text-body-secondary">(optional)</span></label>
            <textarea id="p-description" className="form-control" rows={2}
              value={values.description} onChange={set('description')} />
          </div>
          <div className="col-sm-4">
            <label className="form-label" htmlFor="p-cost">Unit cost (₹)</label>
            <input id="p-cost" className="form-control" required type="number" min="0" step="0.01" inputMode="decimal"
              value={values.unit_cost} onChange={set('unit_cost')} />
          </div>
          <div className="col-sm-4">
            <label className="form-label" htmlFor="p-stock">{editing ? 'Current stock' : 'Opening stock'}</label>
            <input id="p-stock" className="form-control" type="number" min="0" step="1" required
              value={values.current_stock} onChange={set('current_stock')} disabled={editing} aria-describedby="p-stock-help" />
            <div id="p-stock-help" className="form-text">
              {editing ? 'Change stock on the Inventory page.' : 'Recorded as an opening stock movement.'}
            </div>
          </div>
          <div className="col-sm-4">
            <label className="form-label" htmlFor="p-reorder-qty">Reorder quantity</label>
            <input id="p-reorder-qty" className="form-control" type="number" min="0" step="1" required
              value={values.reorder_quantity} onChange={set('reorder_quantity')} />
          </div>
          <div className="col-sm-6">
            <label className="form-label" htmlFor="p-reorder-point">Reorder point</label>
            <input id="p-reorder-point" className="form-control" type="number" min="0" step="1" required
              value={values.reorder_point} onChange={set('reorder_point')} aria-describedby="p-thresholds-help" />
          </div>
          <div className="col-sm-6">
            <label className="form-label" htmlFor="p-minimum">Minimum stock</label>
            <input id="p-minimum" className="form-control" type="number" min="0" step="1" required
              value={values.minimum_stock} onChange={set('minimum_stock')} aria-describedby="p-thresholds-help" />
          </div>
          <div id="p-thresholds-help" className="col-12 form-text mt-1">
            Low-stock alerts start at the reorder point; minimum stock (must not exceed it) marks high severity.
          </div>
        </div>
      </form>
    </Modal>
  )
}
