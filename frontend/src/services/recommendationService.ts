import type { Recommendation, RecommendationListParams } from '../types/recommendation'
import { apiGet } from './api'

export const listRecommendations = (params?: RecommendationListParams) =>
  apiGet<Recommendation[]>('/ai/recommendations', { ...params })
