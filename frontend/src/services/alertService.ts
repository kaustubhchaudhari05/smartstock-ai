import type { Alert, AlertListParams } from '../types/alert'
import { apiGet } from './api'

export const listAlerts = (params?: AlertListParams) => apiGet<Alert[]>('/alerts', { ...params })
