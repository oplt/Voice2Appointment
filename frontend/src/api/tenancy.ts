import { api } from './client'

export type OrgRole = 'owner' | 'admin' | 'manager' | 'staff' | 'viewer'

export type OrganizationSummary = {
  id: number
  name: string
  slug: string
  role: OrgRole | string
  active: boolean
}

export type Organization = {
  id: number
  name: string
  slug: string
}

export type Location = {
  id: number
  name: string
  timezone: string
  address: string | null
  phone: string | null
  business_hours: Record<string, unknown>
}

export type LocationWrite = {
  name: string
  timezone?: string
  address?: string | null
  phone?: string | null
  business_hours?: Record<string, unknown>
}

export type LocationPatch = Partial<LocationWrite>

export type OrgMember = {
  user_id: number
  role: OrgRole | string
  email?: string | null
  username?: string | null
}

export type OrgInvitation = {
  id: number
  email: string
  role: OrgRole | string
  expires_at: string
  accepted_at: string | null
}

export type OrgInvitationCreated = OrgInvitation & {
  token: string
}

const MANAGE_ROLES = new Set(['owner', 'admin'])
const LOCATION_WRITE_ROLES = new Set(['owner', 'admin', 'manager'])
const CUSTOMER_WRITE_ROLES = new Set(['owner', 'admin', 'manager', 'staff'])

export function canManageOrganization(role: string | null | undefined): boolean {
  return MANAGE_ROLES.has((role || '').toLowerCase())
}

export function canWriteLocations(role: string | null | undefined): boolean {
  return LOCATION_WRITE_ROLES.has((role || '').toLowerCase())
}

export function canWriteCustomers(role: string | null | undefined): boolean {
  return CUSTOMER_WRITE_ROLES.has((role || '').toLowerCase())
}

export function listOrganizations(signal?: AbortSignal) {
  return api.get<OrganizationSummary[]>('/api/v1/organizations', { signal })
}

export function activateOrganization(organizationId: number) {
  return api.post<Organization>(`/api/v1/organizations/${organizationId}/activate`)
}

export function getActiveOrganization() {
  return api.get<Organization>('/api/v1/organizations/me')
}

export function listLocations() {
  return api.get<Location[]>('/api/v1/locations')
}

export function createLocation(body: LocationWrite) {
  return api.post<Location>('/api/v1/locations', body)
}

export function patchLocation(locationId: number, body: LocationPatch) {
  return api.patch<Location>(`/api/v1/locations/${locationId}`, body)
}

export function listMembers() {
  return api.get<OrgMember[]>('/api/v1/organizations/members')
}

export function patchMemberRole(userId: number, role: OrgRole) {
  return api.patch<OrgMember>(`/api/v1/organizations/members/${userId}`, { role })
}

export function removeMember(userId: number) {
  return api.delete<void>(`/api/v1/organizations/members/${userId}`)
}

export function listInvitations() {
  return api.get<OrgInvitation[]>('/api/v1/organizations/invitations')
}

export function createInvitation(body: { email: string; role: OrgRole }) {
  return api.post<OrgInvitationCreated>('/api/v1/organizations/invitations', body)
}

export function acceptInvitation(token: string) {
  return api.post<OrgMember>('/api/v1/organizations/invitations/accept', { token })
}
