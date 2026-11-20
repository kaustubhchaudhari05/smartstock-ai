/** Response of GET /api/health */
export interface AppHealth {
  status: string
  app: string
  environment: string
}

/** Response of GET /api/health/db (200 when connected; 503 with `detail` otherwise) */
export interface DatabaseHealth {
  status: string
  database: string
}
