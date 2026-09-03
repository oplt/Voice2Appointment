import { useCallback, useEffect, useState } from 'react'

import { ApiError } from '../api/client'
import { healthRequest } from '../api/auth'

type HealthState = {
  status: 'idle' | 'loading' | 'ok' | 'error'
  message: string | null
  refresh: () => void
}

/** Lightweight server health probe — local state only (PHASE 10). */
export function useApiHealth(auto = true): HealthState {
  const [status, setStatus] = useState<HealthState['status']>('idle')
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setStatus('loading')
    setMessage(null)
    healthRequest()
      .then((data) => {
        setStatus(data.status === 'ok' ? 'ok' : 'error')
        setMessage(data.status)
      })
      .catch((err: unknown) => {
        setStatus('error')
        setMessage(err instanceof ApiError ? err.message : 'API unreachable')
      })
  }, [])

  useEffect(() => {
    if (auto) {
      refresh()
    }
  }, [auto, refresh])

  return { status, message, refresh }
}
