import { api } from './client'

export type Resource = {
  id: number
  name: string
  resource_type: string
  location_id: number | null
  active: boolean
  capacity: number
}

export type ResourceCapability = {
  id: number
  resource_id: number
  capability: string
}

export type AvailabilityRule = {
  id: number
  resource_id: number | null
  location_id: number | null
  weekday: number
  start_time: string
  end_time: string
}

export type AvailabilityException = {
  id: number
  resource_id: number | null
  location_id: number | null
  starts_at: string
  ends_at: string
  available: boolean
  reason: string | null
}

export type ResourceCreate = {
  name: string
  resource_type: string
  location_id?: number | null
  active?: boolean
  capacity?: number
}

export type ResourcePatch = Partial<ResourceCreate>

export type ListResourcesParams = {
  location_id?: number
  resource_type?: string
}

export function listResources(params: ListResourcesParams = {}) {
  const search = new URLSearchParams()
  if (params.location_id != null) search.set('location_id', String(params.location_id))
  if (params.resource_type) search.set('resource_type', params.resource_type)
  const qs = search.toString()
  return api.get<Resource[]>(`/api/v1/resources${qs ? `?${qs}` : ''}`)
}

export function createResource(body: ResourceCreate) {
  return api.post<Resource>('/api/v1/resources', body)
}

export function patchResource(resourceId: number, body: ResourcePatch) {
  return api.patch<Resource>(`/api/v1/resources/${resourceId}`, body)
}

export function listResourceCapabilities(resourceId: number) {
  return api.get<ResourceCapability[]>(`/api/v1/resources/${resourceId}/capabilities`)
}

export function createResourceCapability(resourceId: number, capability: string) {
  return api.post<ResourceCapability>(`/api/v1/resources/${resourceId}/capabilities`, {
    capability,
  })
}

export function listResourceAvailability(resourceId: number) {
  return api.get<AvailabilityRule[]>(`/api/v1/resources/${resourceId}/availability`)
}

export function createResourceAvailability(
  resourceId: number,
  body: { weekday: number; start_time: string; end_time: string },
) {
  return api.post<AvailabilityRule>(`/api/v1/resources/${resourceId}/availability`, body)
}

export function createResourceAvailabilityException(
  resourceId: number,
  body: {
    starts_at: string
    ends_at: string
    available?: boolean
    reason?: string | null
  },
) {
  return api.post<AvailabilityException>(
    `/api/v1/resources/${resourceId}/availability-exceptions`,
    body,
  )
}
