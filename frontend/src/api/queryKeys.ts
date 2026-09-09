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
    items: (filters?: Record<string, unknown>) =>
      ['catalog', 'items', filters ?? {}] as const,
    categories: ['catalog', 'categories'] as const,
  },
  pricing: {
    all: ['pricing'] as const,
    books: ['pricing', 'books'] as const,
    prices: (bookId: number) => ['pricing', 'prices', bookId] as const,
  },
  resources: {
    all: ['resources'] as const,
    list: ['resources', 'list'] as const,
    capabilities: (resourceId: number) =>
      ['resources', 'capabilities', resourceId] as const,
    availability: (resourceId: number) =>
      ['resources', 'availability', resourceId] as const,
  },
  customers: {
    all: ['customers'] as const,
    list: (query?: string) => ['customers', 'list', query ?? ''] as const,
  },
  reservations: {
    all: ['reservations'] as const,
    list: (status?: string) => ['reservations', 'list', status ?? ''] as const,
  },
  knowledge: {
    all: ['knowledge'] as const,
    list: ['knowledge', 'list'] as const,
  },
  industryProfile: {
    all: ['industry-profile'] as const,
    current: ['industry-profile', 'current'] as const,
  },
} as const
