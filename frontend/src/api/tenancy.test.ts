import { describe, expect, it } from 'vitest'

import {
  canManageOrganization,
  canWriteCustomers,
  canWriteLocations,
} from './tenancy'

describe('tenancy RBAC helpers', () => {
  it('gates organization manage to owner/admin', () => {
    expect(canManageOrganization('owner')).toBe(true)
    expect(canManageOrganization('admin')).toBe(true)
    expect(canManageOrganization('manager')).toBe(false)
    expect(canManageOrganization('staff')).toBe(false)
  })

  it('allows managers to write locations', () => {
    expect(canWriteLocations('manager')).toBe(true)
    expect(canWriteLocations('staff')).toBe(false)
  })

  it('allows staff to write customers', () => {
    expect(canWriteCustomers('staff')).toBe(true)
    expect(canWriteCustomers('viewer')).toBe(false)
  })
})
