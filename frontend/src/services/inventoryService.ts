import type { InventoryOverview } from '../types/inventory'
import { apiGet } from './api'

export const getInventoryOverview = (params?: { category?: string; include_inactive?: boolean }) =>
  apiGet<InventoryOverview>('/inventory', params)
