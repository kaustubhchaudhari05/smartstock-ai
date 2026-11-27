import { Route, Routes } from 'react-router'
import AppLayout from './layouts/AppLayout'
import NotFoundPage from './pages/NotFoundPage'
import PlaceholderPage from './pages/PlaceholderPage'

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<PlaceholderPage title="Dashboard" subtitle="Stock overview, alerts and pending decisions" icon="speedometer2" />} />
        <Route path="products" element={<PlaceholderPage title="Products" subtitle="Product catalogue and stock thresholds" icon="box-seam" />} />
        <Route path="inventory" element={<PlaceholderPage title="Inventory" subtitle="Current stock and movement history" icon="boxes" />} />
        <Route path="sales" element={<PlaceholderPage title="Sales Analytics" subtitle="Demand, trends and days of stock remaining" icon="graph-up" />} />
        <Route path="alerts" element={<PlaceholderPage title="Alerts" subtitle="Low-stock and out-of-stock alerts" icon="exclamation-triangle" />} />
        <Route path="ai-insights" element={<PlaceholderPage title="AI Insights" subtitle="AI replenishment recommendations" icon="stars" />} />
        <Route path="purchase-orders" element={<PlaceholderPage title="Purchase Orders" subtitle="Drafts, approvals and order status" icon="receipt" />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
