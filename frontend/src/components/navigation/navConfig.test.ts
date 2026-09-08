import { describe, expect, it } from 'vitest'

import {
  NAV_COLLAPSED_WIDTH,
  NAV_EXPANDED_WIDTH,
  NAV_SECTIONS,
  findActiveNavItem,
  pathMatchesItem,
} from './navConfig'

describe('Phase 9 navigation IA', () => {
  it('keeps permanent nav to the recommended hierarchy', () => {
    expect(NAV_SECTIONS.map((section) => section.id)).toEqual([
      'today',
      'operations',
      'business',
      'insights',
      'system',
    ])
    const labels = NAV_SECTIONS.flatMap((section) =>
      section.items.map((item) => item.label),
    )
    expect(labels).toEqual([
      'Dashboard',
      'Bookings',
      'Calls',
      'Services & Products',
      'Resources',
      'Customers',
      'Analytics',
      'Agent',
      'Integrations',
      'Settings',
    ])
    expect(labels).not.toContain('Calendar')
    expect(labels).not.toContain('Logout')
  })

  it('uses collapsible desktop widths', () => {
    expect(NAV_COLLAPSED_WIDTH).toBe(72)
    expect(NAV_EXPANDED_WIDTH).toBeGreaterThanOrEqual(220)
    expect(NAV_EXPANDED_WIDTH).toBeLessThanOrEqual(240)
  })

  it('maps legacy booking paths onto Bookings', () => {
    const bookings = NAV_SECTIONS.flatMap((s) => s.items).find((i) => i.id === 'bookings')
    expect(bookings).toBeTruthy()
    expect(pathMatchesItem('/appointments', bookings!)).toBe(true)
    expect(pathMatchesItem('/calendar', bookings!)).toBe(true)
    expect(pathMatchesItem('/reservations', bookings!)).toBe(true)
    expect(findActiveNavItem('/appointments')?.label).toBe('Bookings')
  })
})
