import { api } from './client'
import type { AvailabilitySlot, CalendarEvent, CalendarStatus } from '../types'

export type CalendarEventsResponse = { items: CalendarEvent[]; effective_timezone: string }

export function getCalendarStatus() {
  return api.get<CalendarStatus>('/api/v1/calendars/status')
}

export function startGoogleCalendarConnect() {
  return api.get<{ authorization_url: string }>('/api/v1/calendars/google/connect')
}

export function updateCalendarPreferences(body: {
  calendar_id?: string | null
  time_zone?: string | null
}) {
  return api.patch<CalendarStatus>('/api/v1/calendars/preferences', body)
}

export async function listCalendarEvents(params: { timeMin: string; timeMax: string; timezone?: string }) {
  const query = new URLSearchParams({
    timeMin: params.timeMin,
    timeMax: params.timeMax,
  })
  if (params.timezone) query.set('timezone', params.timezone)
  return api.get<CalendarEventsResponse>(
    `/api/v1/calendars/events?${query.toString()}`,
  )
}

export function getCalendarEmbed(viewType = 'week') {
  return api.get<{ embed_url: string }>(`/api/v1/calendars/embed/${viewType}`)
}

export type AvailabilityResponse =
  | AvailabilitySlot[]
  | { slots: AvailabilitySlot[]; available?: boolean }

export function checkCalendarAvailability(params: { start: string; end: string }) {
  const query = new URLSearchParams({
    datetime_start: params.start,
    datetime_end: params.end,
  })
  return api.get<AvailabilityResponse>(`/api/v1/calendars/availability?${query.toString()}`)
}

export function disconnectGoogleCalendar() {
  return api.delete<{ message?: string }>('/api/v1/calendars/google')
}
