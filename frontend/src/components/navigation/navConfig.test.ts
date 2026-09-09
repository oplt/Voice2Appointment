import { describe, expect, it } from 'vitest'

import {
  NAV_COLLAPSED_WIDTH,
  NAV_EXPANDED_WIDTH,
  NAV_SECTIONS,
  UTILITY_NAV_ITEMS,
  findActiveNavItem,
  pathMatchesItem,
  navSectionsForFeatures,
} from './navConfig'

describe('Phase 5 navigation IA', () => {
  it('keeps permanent nav to the operational hierarchy', () => {
    expect(NAV_SECTIONS.map((section) => section.id)).toEqual([
      'today',
      'bookings',
      'customers',
      'operations',
      'assistant',
      'insights',
    ])
    const labels = NAV_SECTIONS.flatMap((section) =>
      section.items.map((item) => item.label),
    )
    expect(labels).toEqual([
      'Dashboard',
      'Bookings',
      'Customers',
      'Calls',
      'Services & Products',
      'Resources',
      'Agent',
      'Analytics',
    ])
    expect(labels).not.toContain('Calendar')
    expect(labels).not.toContain('Integrations')
    expect(labels).not.toContain('Settings')
    expect(labels).not.toContain('Logout')
  })

  it('moves Integrations and Settings into utility navigation', () => {
    expect(UTILITY_NAV_ITEMS.map((item) => item.id)).toEqual([
      'integrations',
      'settings',
    ])
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

  it('hides catalog and booking nav when kill switches are off', () => {
    const sections = navSectionsForFeatures({
      catalog_domain: false,
      reservation_domain: false,
      industry_voice_tools: false,
    })

    const labels = sections.flatMap((s) => s.items.map((i) => i.id))
    expect(labels).not.toContain('catalog')
    expect(labels).not.toContain('bookings')
  })
})
