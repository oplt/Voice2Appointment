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

export type ResourcePatch = Partial<ResourceCreate> & {
  force?: boolean
}

export type ListResourcesParams = {
  location_id?: number
  resource_type?: string
  include_inactive?: boolean
}

export function listResources(params: ListResourcesParams = {}) {
  const search = new URLSearchParams()
  if (params.location_id != null) search.set('location_id', String(params.location_id))
  if (params.resource_type) search.set('resource_type', params.resource_type)
  if (params.include_inactive) search.set('include_inactive', 'true')
  const qs = search.toString()
  return api.get<Resource[]>(`/api/v1/resources${qs ? `?${qs}` : ''}`)
}

export function createResource(body: ResourceCreate) {
  return api.post<Resource>('/api/v1/resources', body)
}

export function patchResource(
  resourceId: number,
  body: ResourcePatch,
  options: { force?: boolean } = {},
) {
  const { force, ...payload } = body
  const useForce = options.force ?? force
  const qs = useForce ? '?force=true' : ''
  return api.patch<Resource>(`/api/v1/resources/${resourceId}${qs}`, payload)
}

export function listResourceCapabilities(resourceId: number) {
  return api.get<ResourceCapability[]>(`/api/v1/resources/${resourceId}/capabilities`)
}

export function createResourceCapability(resourceId: number, capability: string) {
  return api.post<ResourceCapability>(`/api/v1/resources/${resourceId}/capabilities`, {
    capability,
  })
}

export function patchResourceCapability(
  resourceId: number,
  capabilityId: number,
  capability: string,
) {
  return api.patch<ResourceCapability>(
    `/api/v1/resources/${resourceId}/capabilities/${capabilityId}`,
    { capability },
  )
}

export function deleteResourceCapability(resourceId: number, capabilityId: number) {
  return api.delete<void>(`/api/v1/resources/${resourceId}/capabilities/${capabilityId}`)
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

export function patchResourceAvailability(
  resourceId: number,
  ruleId: number,
  body: { weekday?: number; start_time?: string; end_time?: string },
) {
  return api.patch<AvailabilityRule>(
    `/api/v1/resources/${resourceId}/availability/${ruleId}`,
    body,
  )
}

export function deleteResourceAvailability(resourceId: number, ruleId: number) {
  return api.delete<void>(`/api/v1/resources/${resourceId}/availability/${ruleId}`)
}

export function listResourceAvailabilityExceptions(resourceId: number) {
  return api.get<AvailabilityException[]>(
    `/api/v1/resources/${resourceId}/availability-exceptions`,
  )
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

export function patchResourceAvailabilityException(
  resourceId: number,
  exceptionId: number,
  body: {
    starts_at?: string
    ends_at?: string
    available?: boolean
    reason?: string | null
  },
) {
  return api.patch<AvailabilityException>(
    `/api/v1/resources/${resourceId}/availability-exceptions/${exceptionId}`,
    body,
  )
}

export function deleteResourceAvailabilityException(
  resourceId: number,
  exceptionId: number,
) {
  return api.delete<void>(
    `/api/v1/resources/${resourceId}/availability-exceptions/${exceptionId}`,
  )
}
