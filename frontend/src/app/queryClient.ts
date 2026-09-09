import { QueryClient } from '@tanstack/react-query'

/**
 * Shared defaults (Phase 5): prefer mutation-driven invalidation for config data.
 * Per-query staleTime should override these by domain semantics.
 */
export function createAppQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        gcTime: 5 * 60_000,
        retry: 1,
        refetchOnWindowFocus: false,
        refetchOnReconnect: true,
      },
      mutations: {
        retry: 0,
      },
    },
  })
}

/** Suggested stale times by data semantics. */
export const queryStaleTime = {
  calls: 15_000,
  reservations: 15_000,
  dashboard: 20_000,
  analytics: 60_000,
  catalog: 5 * 60_000,
  resources: 5 * 60_000,
  customers: 60_000,
  settings: 5 * 60_000,
  tenancy: 5 * 60_000,
} as const
