import type { ReactNode } from 'react'

import type { GlobalFeatureFlags } from '../../types'

export type NavItem = {
  id: string
  label: string
  to: string
  match?: string[]
}

export type NavSection = {
  id: string
  label: string
  items: NavItem[]
}

/**
 * Primary operational navigation (Phase 5).
 * Integrations and Settings live in the account utility menu.
 */
export const NAV_SECTIONS: NavSection[] = [
  {
    id: 'today',
    label: 'Today',
    items: [{ id: 'dashboard', label: 'Dashboard', to: '/dashboard' }],
  },
  {
    id: 'bookings',
    label: 'Bookings',
    items: [
      {
        id: 'bookings',
        label: 'Bookings',
        to: '/reservations',
        match: ['/reservations', '/appointments', '/calendar'],
      },
    ],
  },
  {
    id: 'customers',
    label: 'Customers',
    items: [{ id: 'customers', label: 'Customers', to: '/customers' }],
  },
  {
    id: 'operations',
    label: 'Operations',
    items: [
      { id: 'calls', label: 'Calls', to: '/calls' },
      { id: 'catalog', label: 'Services & Products', to: '/catalog' },
      { id: 'resources', label: 'Resources', to: '/resources' },
    ],
  },
  {
    id: 'assistant',
    label: 'Assistant',
    items: [{ id: 'agent', label: 'Agent', to: '/agent' }],
  },
  {
    id: 'insights',
    label: 'Insights',
    items: [{ id: 'analytics', label: 'Analytics', to: '/analytics' }],
  },
]

/** Utility destinations shown in the account menu, not the primary sidebar. */
export const UTILITY_NAV_ITEMS: NavItem[] = [
  { id: 'integrations', label: 'Integrations', to: '/integrations' },
  { id: 'settings', label: 'Settings', to: '/settings' },
]

export const NAV_COLLAPSED_WIDTH = 72
export const NAV_EXPANDED_WIDTH = 232
export const NAV_COLLAPSE_STORAGE_KEY = 'va.nav.collapsed'

export function pathMatchesItem(pathname: string, item: NavItem): boolean {
  const candidates = item.match ?? [item.to]
  return candidates.some(
    (path) => pathname === path || pathname.startsWith(`${path}/`),
  )
}

export function findActiveNavItem(pathname: string): NavItem | null {
  for (const section of NAV_SECTIONS) {
    for (const item of section.items) {
      if (pathMatchesItem(pathname, item)) {
        return item
      }
    }
  }
  for (const item of UTILITY_NAV_ITEMS) {
    if (pathMatchesItem(pathname, item)) {
      return item
    }
  }
  return null
}

export type NavIconMap = Record<string, ReactNode>

/**
 * Apply global kill switches to navigation.
 *
 * Contract (Phase 3): when a domain flag is OFF, the corresponding HTTP surface
 * is unavailable, so users should not be offered predictable 404 flows.
 */
export function navSectionsForFeatures(
  features: GlobalFeatureFlags | null | undefined,
): NavSection[] {
  if (!features) return NAV_SECTIONS

  const catalogAllowed = Boolean(features.catalog_domain)
  const reservationAllowed = Boolean(features.reservation_domain)

  const filtered = NAV_SECTIONS.map((section) => {
    return {
      ...section,
      items: section.items.filter((item) => {
        if (item.id === 'catalog' && !catalogAllowed) return false
        if (item.id === 'bookings' && !reservationAllowed) return false
        return true
      }),
    }
  }).filter((section) => section.items.length > 0)

  return filtered
}
