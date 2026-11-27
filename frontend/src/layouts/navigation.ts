/** Sidebar entries. `icon` is a Bootstrap Icons name (https://icons.getbootstrap.com). */
export interface NavItem {
  to: string
  label: string
  icon: string
}

export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', icon: 'speedometer2' },
  { to: '/products', label: 'Products', icon: 'box-seam' },
  { to: '/inventory', label: 'Inventory', icon: 'boxes' },
  { to: '/sales', label: 'Sales Analytics', icon: 'graph-up' },
  { to: '/alerts', label: 'Alerts', icon: 'exclamation-triangle' },
  { to: '/ai-insights', label: 'AI Insights', icon: 'stars' },
  { to: '/purchase-orders', label: 'Purchase Orders', icon: 'receipt' },
]
