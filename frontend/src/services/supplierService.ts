import type { Supplier } from '../types/supplier'
import { apiGet } from './api'

export const listSuppliers = (params?: { search?: string; include_inactive?: boolean; limit?: number }) =>
  apiGet<Supplier[]>('/suppliers', params)
