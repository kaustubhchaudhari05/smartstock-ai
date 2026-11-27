import { Route, Routes } from 'react-router'
import AppLayout from './layouts/AppLayout'
import DashboardPage from './pages/DashboardPage'
import InventoryPage from './pages/inventory/InventoryPage'
import NotFoundPage from './pages/NotFoundPage'
import ProductsPage from './pages/products/ProductsPage'
import SalesPage from './pages/sales/SalesPage'
import PlaceholderPage from './pages/PlaceholderPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="inventory" element={<InventoryPage />} />
        <Route path="sales" element={<SalesPage />} />
        <Route path="alerts" element={<PlaceholderPage title="Alerts" subtitle="Low-stock and out-of-stock alerts" icon="exclamation-triangle" />} />
        <Route path="ai-insights" element={<PlaceholderPage title="AI Insights" subtitle="AI replenishment recommendations" icon="stars" />} />
        <Route path="purchase-orders" element={<PlaceholderPage title="Purchase Orders" subtitle="Drafts, approvals and order status" icon="receipt" />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
