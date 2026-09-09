import { useQuery } from '@tanstack/react-query'

import {
  listCatalogItems,
  listResourceRequirements,
} from '../../api/catalog'
import { queryKeys } from '../../api/queryKeys'
import { listLocations } from '../../api/pricing'
import {
  listResourceAvailability,
  listResourceAvailabilityExceptions,
  listResourceCapabilities,
  listResources,
} from '../../api/resources'
import { queryStaleTime } from '../../app/queryClient'

export const DETAIL_TABS = [
  'Overview',
  'Capabilities',
  'Working hours',
  'Service assignments',
  'Time off',
] as const

export const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

export function toDatetimeLocalValue(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

export function fromDatetimeLocalValue(value: string): string {
  return new Date(value).toISOString()
}

export function useResourcesListQuery() {
  return useQuery({
    queryKey: queryKeys.resources.list,
    queryFn: ({ signal }) => listResources({ include_inactive: true }, signal),
    staleTime: queryStaleTime.resources,
  })
}

export function useResourceLocationsQuery() {
  return useQuery({
    queryKey: queryKeys.pricing.locations,
    queryFn: ({ signal }) => listLocations(signal),
    staleTime: queryStaleTime.resources,
  })
}

export function useResourceCapabilitiesQuery(resourceId: number | null) {
  return useQuery({
    queryKey: queryKeys.resources.capabilities(resourceId ?? 0),
    queryFn: ({ signal }) => listResourceCapabilities(resourceId!, signal),
    enabled: resourceId != null,
    staleTime: queryStaleTime.resources,
  })
}

export function useResourceAvailabilityQuery(
  resourceId: number | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.resources.availability(resourceId ?? 0),
    queryFn: ({ signal }) => listResourceAvailability(resourceId!, signal),
    enabled: resourceId != null && enabled,
    staleTime: queryStaleTime.resources,
  })
}

export function useResourceExceptionsQuery(
  resourceId: number | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.resources.exceptions(resourceId ?? 0),
    queryFn: ({ signal }) => listResourceAvailabilityExceptions(resourceId!, signal),
    enabled: resourceId != null && enabled,
    staleTime: queryStaleTime.resources,
  })
}

export function useAssignableServicesQuery(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.catalog.items({ forResourceAssign: true, kind: 'service' }),
    queryFn: ({ signal }) =>
      listCatalogItems({ kind: 'service', limit: 100, active: true }, signal),
    enabled,
    staleTime: queryStaleTime.catalog,
  })
}

export function useServiceRequirementsQuery(
  serviceId: number | '',
  enabled: boolean,
) {
  return useQuery({
    queryKey: queryKeys.catalog.requirements(serviceId === '' ? 0 : serviceId),
    queryFn: ({ signal }) => listResourceRequirements(serviceId as number, signal),
    enabled: enabled && serviceId !== '',
    staleTime: queryStaleTime.catalog,
  })
}
