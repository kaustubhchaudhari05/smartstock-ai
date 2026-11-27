import { useCallback, useMemo, useState } from 'react'
import EmptyState from '../../components/EmptyState'
import ErrorState from '../../components/ErrorState'
import LoadingState from '../../components/LoadingState'
import PageHeader from '../../components/PageHeader'
import StatusBadge from '../../components/StatusBadge'
import { useApi } from '../../hooks/useApi'
import { useDebouncedValue } from '../../hooks/useDebouncedValue'
import { listProducts } from '../../services/productService'
import { listSuppliers } from '../../services/supplierService'
import type { Product } from '../../types/product'
import { formatMoney, formatNumber } from '../../utils/format'
import ProductDetailModal from './ProductDetailModal'
import ProductFormModal from './ProductFormModal'

const MAX_ROWS = 500 // backend limit per request

// Reference data for filters and the form (stable loaders, see useApi).
const loadAllProducts = () => listProducts({ include_inactive: true, limit: MAX_ROWS })
const loadSuppliers = () => listSuppliers({ include_inactive: true, limit: MAX_ROWS })

type Dialog = { mode: 'view' | 'edit'; product: Product } | { mode: 'create' } | null

export default function ProductsPage() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('')
  const [includeInactive, setIncludeInactive] = useState(false)
  const [dialog, setDialog] = useState<Dialog>(null)
  const debouncedSearch = useDebouncedValue(search.trim())

  // The list itself is filtered by the backend (search on name/SKU, category, active flag).
  const loadProducts = useCallback(
    () =>
      listProducts({
        search: debouncedSearch || undefined,
        category: category || undefined,
        include_inactive: includeInactive,
        limit: MAX_ROWS,
      }),
    [debouncedSearch, category, includeInactive],
  )
  const products = useApi(loadProducts)
  const allProducts = useApi(loadAllProducts)
  const suppliers = useApi(loadSuppliers)

  const categories = useMemo(
    () => [...new Set((allProducts.data ?? []).map((p) => p.category))].sort((a, b) => a.localeCompare(b)),
    [allProducts.data],
  )
  const filtered = Boolean(debouncedSearch || category)

  function afterSave(saved: Product) {
    products.reload()
    allProducts.reload()
    setDialog({ mode: 'view', product: saved })
  }

  return (
    <>
      <PageHeader
        title="Products"
        subtitle="Product catalogue, suppliers and stock thresholds"
        actions={
          <button type="button" className="btn btn-primary" onClick={() => setDialog({ mode: 'create' })}>
            <i className="bi bi-plus-lg me-1" aria-hidden="true" />
            New product
          </button>
        }
      />

      <div className="card">
        <div className="card-body border-bottom">
          <div className="row g-2 align-items-center">
            <div className="col-12 col-md-5">
              <div className="input-group">
                <span className="input-group-text" aria-hidden="true">
                  <i className="bi bi-search" />
                </span>
                <input
                  type="search"
                  className="form-control"
                  placeholder="Search name or SKU"
                  aria-label="Search name or SKU"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                />
              </div>
            </div>
            <div className="col-8 col-md-4">
              <select
                className="form-select"
                aria-label="Category"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
              >
                <option value="">All categories</option>
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-4 col-md-3">
              <div className="form-check form-switch mb-0">
                <input
                  id="show-inactive"
                  className="form-check-input"
                  type="checkbox"
                  role="switch"
                  checked={includeInactive}
                  onChange={(e) => setIncludeInactive(e.target.checked)}
                />
                <label className="form-check-label" htmlFor="show-inactive">
                  Show inactive
                </label>
              </div>
            </div>
          </div>
        </div>

        {products.error && (
          <div className="card-body">
            <ErrorState error={products.error} onRetry={products.reload} />
          </div>
        )}
        {!products.data && products.loading && <LoadingState label="Loading products…" />}
        {products.data && products.data.length === 0 && (
          <EmptyState
            icon={filtered ? 'search' : 'box-seam'}
            title={filtered ? 'No matching products' : 'No products yet'}
            message={filtered ? 'Try another search or category.' : 'Create your first product to start tracking stock.'}
          />
        )}
        {products.data && products.data.length > 0 && (
          <>
            <div className="table-responsive">
              <table className="table table-hover align-middle mb-0">
                <thead>
                  <tr>
                    <th scope="col">Product</th>
                    <th scope="col" className="d-none d-md-table-cell">Category</th>
                    <th scope="col" className="d-none d-lg-table-cell">Supplier</th>
                    <th scope="col" className="text-end">Stock</th>
                    <th scope="col">Status</th>
                    <th scope="col" className="text-end d-none d-sm-table-cell">Unit cost</th>
                    <th scope="col"><span className="visually-hidden">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {products.data.map((p) => (
                    <tr key={p.id} className={p.is_active ? '' : 'text-body-secondary'}>
                      <td>
                        <button
                          type="button"
                          className="btn btn-link p-0 text-start text-decoration-none fw-semibold"
                          onClick={() => setDialog({ mode: 'view', product: p })}
                        >
                          {p.name}
                        </button>
                        <div className="small text-body-secondary">{p.sku}</div>
                      </td>
                      <td className="d-none d-md-table-cell">{p.category}</td>
                      <td className="d-none d-lg-table-cell">
                        {p.supplier?.name ?? <span className="text-body-secondary">None</span>}
                      </td>
                      <td className="text-end">
                        <div className="fw-semibold">{formatNumber(p.current_stock)}</div>
                        <div className="small text-body-secondary text-nowrap">
                          reorder at {formatNumber(p.reorder_point)}
                        </div>
                      </td>
                      <td>
                        {p.is_active ? (
                          <StatusBadge kind="inventory" value={p.inventory_status} />
                        ) : (
                          <span className="badge text-bg-dark">Inactive</span>
                        )}
                      </td>
                      <td className="text-end d-none d-sm-table-cell">{formatMoney(p.unit_cost)}</td>
                      <td className="text-end">
                        <button
                          type="button"
                          className="btn btn-sm btn-outline-secondary"
                          onClick={() => setDialog({ mode: 'edit', product: p })}
                          aria-label={`Edit ${p.name}`}
                          title="Edit"
                        >
                          <i className="bi bi-pencil" aria-hidden="true" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="card-footer small text-body-secondary bg-body">
              {formatNumber(products.data.length)} product{products.data.length === 1 ? '' : 's'}
              {products.loading && <span className="spinner-border spinner-border-sm ms-2" aria-label="Refreshing" />}
            </div>
          </>
        )}
      </div>

      {dialog?.mode === 'view' && (
        <ProductDetailModal
          product={dialog.product}
          onClose={() => setDialog(null)}
          onEdit={() => setDialog({ mode: 'edit', product: dialog.product })}
          onChanged={(changed) => {
            products.reload()
            setDialog({ mode: 'view', product: changed })
          }}
        />
      )}
      {(dialog?.mode === 'edit' || dialog?.mode === 'create') && (
        <ProductFormModal
          product={dialog.mode === 'edit' ? dialog.product : undefined}
          suppliers={suppliers.data ?? []}
          categories={categories}
          onClose={() => setDialog(null)}
          onSaved={afterSave}
        />
      )}
    </>
  )
}
