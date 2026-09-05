import { api } from './client'
import type { AnalyticsMeta } from '../features/analytics/filters'
import type { AnalyticsSummary } from '../types'

export function getAnalyticsMeta() {
  return api.get<AnalyticsMeta>('/api/v1/analytics/meta')
}

export function getAnalyticsSummary(params: {
  start: string
  end: string
  compare?: boolean
}) {
  const query = new URLSearchParams({
    start: params.start,
    end: params.end,
  })
  if (params.compare) query.set('compare', 'true')
  return api.get<AnalyticsSummary>(`/api/v1/analytics/summary?${query.toString()}`)
}

export function fetchTwilioAnalytics() {
  return api.post<{ message?: string; synced?: number; total_calls?: number }>(
    '/api/v1/analytics/fetch-twilio',
  )
}
