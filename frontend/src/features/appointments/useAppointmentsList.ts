import { useCallback, useEffect, useRef, useState } from 'react'

import { listAppointments } from '../../api/appointments'
import { ApiError } from '../../api/client'
import type { AppointmentListItem } from '../../types'

export type AppointmentScope = 'upcoming' | 'history' | 'all'

export function useAppointmentsList() {
  const [items, setItems] = useState<AppointmentListItem[]>([])
  const [scope, setScope] = useState<AppointmentScope>('upcoming')
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const requestId = useRef(0)

  const fetchPage = useCallback(async (reset: boolean, cursor?: string | null) => {
    const currentRequest = ++requestId.current
    reset ? setLoading(true) : setLoadingMore(true)
    setError(null)
    try {
      const page = await listAppointments({ scope, limit: 100, cursor })
      if (currentRequest !== requestId.current) return
      setItems((current) => {
        const source = reset ? [] : current
        const merged = new Map(source.map((item) => [item.id, item]))
        page.items.forEach((item) => merged.set(item.id, item))
        return [...merged.values()]
      })
      setNextCursor(page.next_cursor ?? null)
    } catch (caught: unknown) {
      if (currentRequest !== requestId.current) return
      if (reset) setItems([])
      setError(caught instanceof ApiError ? caught.message : 'Failed to load appointments')
    } finally {
      if (currentRequest === requestId.current) {
        setLoading(false)
        setLoadingMore(false)
      }
    }
  }, [scope])

  useEffect(() => {
    void fetchPage(true)
  }, [fetchPage])

  return {
    items,
    scope,
    setScope,
    nextCursor,
    loading,
    loadingMore,
    error,
    refresh: () => fetchPage(true),
    loadMore: () => fetchPage(false, nextCursor),
  }
}
