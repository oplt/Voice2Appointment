import type { ReactNode } from 'react'

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
 * Permanent authenticated navigation (Phase 9 IA).
 * Calendar and other secondary surfaces stay routeable but off the permanent nav.
 */
export const NAV_SECTIONS: NavSection[] = [
  {
    id: 'today',
    label: 'Today',
    items: [{ id: 'dashboard', label: 'Dashboard', to: '/dashboard' }],
  },
  {
    id: 'operations',
    label: 'Operations',
    items: [
      {
        id: 'bookings',
        label: 'Bookings',
        to: '/reservations',
        match: ['/reservations', '/appointments', '/calendar'],
      },
      { id: 'calls', label: 'Calls', to: '/calls' },
    ],
  },
  {
    id: 'business',
    label: 'Business',
    items: [
      { id: 'catalog', label: 'Services & Products', to: '/catalog' },
      { id: 'resources', label: 'Resources', to: '/resources' },
      { id: 'customers', label: 'Customers', to: '/customers' },
    ],
  },
  {
    id: 'insights',
    label: 'Insights',
    items: [{ id: 'analytics', label: 'Analytics', to: '/analytics' }],
  },
  {
    id: 'system',
    label: 'System',
    items: [
      { id: 'agent', label: 'Agent', to: '/agent' },
      { id: 'integrations', label: 'Integrations', to: '/integrations' },
      { id: 'settings', label: 'Settings', to: '/settings' },
    ],
  },
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
  return null
}

export type NavIconMap = Record<string, ReactNode>
