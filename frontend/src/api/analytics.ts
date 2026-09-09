import { api } from './client'
import type { AnalyticsMeta } from '../features/analytics/filters'
import type { AnalyticsSummary } from '../types'

export type TwilioSyncStatus = {
  status: 'queued' | 'syncing' | 'healthy' | 'error'
  last_synced_at: string | null
  error_code: string | null
  updated_at: string | null
  queued_now?: string
}

export function getAnalyticsMeta(signal?: AbortSignal) {
  return api.get<AnalyticsMeta & { twilio_sync?: TwilioSyncStatus }>(
    '/api/v1/analytics/meta',
    { signal },
  )
}

export function getAnalyticsSummary(
  params: {
    start: string
    end: string
    compare?: boolean
  },
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({
    start: params.start,
    end: params.end,
  })
  if (params.compare) query.set('compare', 'true')
  return api.get<AnalyticsSummary>(`/api/v1/analytics/summary?${query.toString()}`, {
    signal,
  })
}

export function fetchTwilioAnalytics() {
  return api.post<TwilioSyncStatus>('/api/v1/analytics/fetch-twilio')
}

export function getTwilioSyncStatus() {
  return api.get<TwilioSyncStatus>('/api/v1/analytics/twilio-sync-status')
}
