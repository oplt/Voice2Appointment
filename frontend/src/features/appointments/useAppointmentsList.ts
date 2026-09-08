import { useInfiniteQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { listAppointments } from '../../api/appointments'
import { ApiError } from '../../api/client'
import { queryKeys } from '../../api/queryKeys'
import type { AppointmentListItem } from '../../types'

export type AppointmentScope = 'upcoming' | 'history' | 'all'

export function useAppointmentsList() {
  const [scope, setScope] = useState<AppointmentScope>('upcoming')

  const query = useInfiniteQuery({
    queryKey: queryKeys.appointments.list(scope),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      listAppointments({ scope, limit: 100, cursor: pageParam }),
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
  })

  const items: AppointmentListItem[] = query.data
    ? (() => {
        const merged = new Map<number, AppointmentListItem>()
        for (const page of query.data.pages) {
          for (const item of page.items) {
            merged.set(item.id, item)
          }
        }
        return [...merged.values()]
      })()
    : []

  const error =
    query.error == null
      ? null
      : query.error instanceof ApiError
        ? query.error.message
        : 'Failed to load appointments'

  return {
    items,
    scope,
    setScope,
    nextCursor: query.hasNextPage
      ? (query.data?.pages.at(-1)?.next_cursor ?? null)
      : null,
    loading: query.isPending,
    loadingMore: query.isFetchingNextPage,
    error,
    refresh: () => {
      void query.refetch()
    },
    loadMore: () => {
      if (query.hasNextPage && !query.isFetchingNextPage) {
        void query.fetchNextPage()
      }
    },
  }
}
