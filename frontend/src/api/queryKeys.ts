export const queryKeys = {
  dashboard: {
    summary: ['dashboard', 'summary'] as const,
  },
  appointments: {
    all: ['appointments'] as const,
    list: (scope: string) => ['appointments', 'list', scope] as const,
  },
  calls: {
    all: ['calls'] as const,
    list: ['calls', 'list'] as const,
    detail: (id: number) => ['calls', 'detail', id] as const,
  },
  analytics: {
    all: ['analytics'] as const,
  },
  catalog: {
    all: ['catalog'] as const,
  },
  pricing: {
    all: ['pricing'] as const,
  },
  resources: {
    all: ['resources'] as const,
  },
  customers: {
    all: ['customers'] as const,
  },
} as const
