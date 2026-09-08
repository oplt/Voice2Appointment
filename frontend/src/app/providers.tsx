import { QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'
import { useState } from 'react'

import { createAppQueryClient } from './queryClient'

type AppProvidersProps = {
  children: ReactNode
}

/** App-level providers. Backend remains authoritative for mutations. */
export function AppProviders({ children }: AppProvidersProps) {
  const [queryClient] = useState(() => createAppQueryClient())
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}
