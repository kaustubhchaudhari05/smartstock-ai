import type { IsoDateTime } from './common'

export type RiskLevel = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type Urgency = 'IMMEDIATE' | 'SOON' | 'ROUTINE' | 'NONE'
export type RecommendationStatus = 'PENDING_REVIEW' | 'ACCEPTED' | 'REJECTED'

/** Item of GET /api/ai/recommendations. `risk_level` is decided by backend rules. */
export interface Recommendation {
  id: number
  product_id: number
  product_sku: string
  product_name: string
  alert_id: number | null
  risk_level: RiskLevel
  urgency: Urgency
  recommendation: string
  suggested_quantity: number
  reasoning: string[]
  status: RecommendationStatus
  model_name: string
  created_at: IsoDateTime
}

/** Query parameters of GET /api/ai/recommendations */
export interface RecommendationListParams {
  product_id?: number
  status?: RecommendationStatus
  risk_level?: RiskLevel
  skip?: number
  limit?: number
}
