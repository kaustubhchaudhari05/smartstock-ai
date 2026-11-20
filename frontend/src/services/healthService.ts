import type { AppHealth, DatabaseHealth } from '../types/health'
import { apiGet } from './api'

export const getAppHealth = () => apiGet<AppHealth>('/health')

export const getDatabaseHealth = () => apiGet<DatabaseHealth>('/health/db')
