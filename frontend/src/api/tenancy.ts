import { api } from './client'

export type OrganizationSummary = {
  id: number
  name: string
  slug: string
  role: string
  active: boolean
}

export function listOrganizations() {
  return api.get<OrganizationSummary[]>('/api/v1/organizations')
}

export function activateOrganization(organizationId: number) {
  return api.post<OrganizationSummary>(`/api/v1/organizations/${organizationId}/activate`)
}

export function getActiveOrganization() {
  return api.get<Pick<OrganizationSummary, 'id' | 'name' | 'slug'>>('/api/v1/organizations/me')
}
