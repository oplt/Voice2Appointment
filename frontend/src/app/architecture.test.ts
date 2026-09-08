/** Architecture smoke: Phase 8 app shell + feature modules exist. */

import { describe, expect, it } from 'vitest'

import { createAppQueryClient } from '../app/queryClient'
import { queryKeys } from '../api/queryKeys'

describe('Phase 8 product architecture', () => {
  it('creates a query client with product defaults', () => {
    const client = createAppQueryClient()
    const defaults = client.getDefaultOptions()
    expect(defaults.queries?.staleTime).toBe(30_000)
    expect(defaults.queries?.retry).toBe(1)
    expect(defaults.mutations?.retry).toBe(0)
  })

  it('exposes stable query keys for feature domains', () => {
    expect(queryKeys.dashboard.summary).toEqual(['dashboard', 'summary'])
    expect(queryKeys.appointments.list('upcoming')).toEqual([
      'appointments',
      'list',
      'upcoming',
    ])
    expect(queryKeys.calls.detail(9)).toEqual(['calls', 'detail', 9])
    expect(queryKeys.catalog.all[0]).toBe('catalog')
  })
})
