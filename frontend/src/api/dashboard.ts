import { api } from './client'
import type { DashboardSummary } from '../types'

export function getDashboardSummary() {
  return api.get<DashboardSummary>('/api/v1/dashboard/summary')
}
