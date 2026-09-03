import { api } from './client'
import type { AnalyticsSummary } from '../types'

export function getAnalyticsSummary(params: { start: string; end: string }) {
  const query = new URLSearchParams({
    start: params.start,
    end: params.end,
  })
  return api.get<AnalyticsSummary>(`/api/v1/analytics/summary?${query.toString()}`)
}

export function fetchTwilioAnalytics() {
  return api.post<{ message?: string; synced?: number; total_calls?: number }>(
    '/api/v1/analytics/fetch-twilio',
  )
}
