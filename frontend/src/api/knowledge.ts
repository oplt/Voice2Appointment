import { api } from './client'

export type KnowledgeEntry = {
  id: number
  title: string
  content: string
  active: boolean
  metadata_json: Record<string, unknown>
}

export type KnowledgeWrite = {
  title: string
  content: string
  active?: boolean
  metadata_json?: Record<string, unknown>
}

export type KnowledgePatch = {
  title?: string
  content?: string
  active?: boolean
  metadata_json?: Record<string, unknown>
}

export type IndustryType = 'clinic' | 'restaurant' | 'salon' | 'general'

export type IndustryProfile = {
  id: number
  industry_type: string
  scheduling_mode: string
  required_customer_fields: unknown[]
  required_booking_fields: unknown[]
  enabled_tools: unknown[]
  confirmation_policy: Record<string, unknown>
  deposit_policy: Record<string, unknown>
  handoff_policy: Record<string, unknown>
  privacy_policy: Record<string, unknown>
  terminology: Record<string, unknown>
  flow_steps: unknown[]
  metadata_json: Record<string, unknown>
}

export type IndustryProfilePut = {
  industry_type: IndustryType
  overrides?: Record<string, unknown>
}

export function listKnowledge() {
  return api.get<KnowledgeEntry[]>('/api/v1/knowledge')
}

export function createKnowledge(body: KnowledgeWrite) {
  return api.post<KnowledgeEntry>('/api/v1/knowledge', body)
}

export function patchKnowledge(entryId: number, body: KnowledgePatch) {
  return api.patch<KnowledgeEntry>(`/api/v1/knowledge/${entryId}`, body)
}

export function getIndustryProfile() {
  return api.get<IndustryProfile | null>('/api/v1/industry-profile')
}

export function putIndustryProfile(body: IndustryProfilePut) {
  return api.put<IndustryProfile>('/api/v1/industry-profile', body)
}
