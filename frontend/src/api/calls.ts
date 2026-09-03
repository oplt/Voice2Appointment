import { api } from './client'
import type { CallSession, CallSessionList } from '../types'

export function listCalls(params?: { limit?: number; cursor?: string | null }) {
  const query = new URLSearchParams()
  if (params?.limit) query.set('limit', String(params.limit))
  if (params?.cursor) query.set('cursor', params.cursor)
  const qs = query.toString()
  return api.get<CallSessionList>(`/api/v1/calls${qs ? `?${qs}` : ''}`)
}

export function getCall(callId: number, includeTranscript = false) {
  const query = includeTranscript ? '?include_transcript=true' : ''
  return api.get<CallSession>(`/api/v1/calls/${callId}${query}`)
}
