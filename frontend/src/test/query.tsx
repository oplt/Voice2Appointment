import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement, ReactNode } from 'react'

import { createAppQueryClient } from '../app/queryClient'

/** Test helper: isolated QueryClient (no shared cache across tests). */
export function withQueryClient(ui: ReactElement): ReactElement {
  const client = createAppQueryClient()
  client.setDefaultOptions({
    queries: { retry: false },
    mutations: { retry: false },
  })
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>
}

export function QueryHarness({ children }: { children: ReactNode }) {
  return withQueryClient(<>{children}</>)
}
