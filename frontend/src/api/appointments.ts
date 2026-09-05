import { api } from './client'
import type {
  Appointment,
  AppointmentCreate,
  AppointmentListItem,
  AppointmentUpdate,
  NotificationDeliveryStatus,
} from '../types'

export type AppointmentsListResponse =
  | AppointmentListItem[]
  | { items: AppointmentListItem[]; next_cursor?: string | null; scope?: string; limit?: number }

export type ListAppointmentsParams = {
  scope?: 'upcoming' | 'history' | 'all'
  limit?: number
  cursor?: string | null
  status?: string
}

function normalizeList(data: AppointmentsListResponse): AppointmentListItem[] {
  return Array.isArray(data) ? data : (data.items ?? [])
}

export async function listAppointments(params: ListAppointmentsParams = {}) {
  const search = new URLSearchParams()
  search.set('scope', params.scope ?? 'upcoming')
  if (params.limit != null) search.set('limit', String(params.limit))
  if (params.cursor) search.set('cursor', params.cursor)
  if (params.status) search.set('status', params.status)
  const qs = search.toString()
  const data = await api.get<AppointmentsListResponse>(
    `/api/v1/appointments/page${qs ? `?${qs}` : ''}`,
  )
  if (Array.isArray(data)) {
    return { items: data, next_cursor: null as string | null }
  }
  return {
    items: normalizeList(data),
    next_cursor: data.next_cursor ?? null,
  }
}

export function createAppointment(body: AppointmentCreate) {
  return api.post<Appointment>('/api/v1/appointments', body)
}

export function getAppointment(id: number) {
  return api.get<Appointment>(`/api/v1/appointments/${id}`)
}

export function updateAppointment(id: number, body: AppointmentUpdate) {
  return api.patch<Appointment>(`/api/v1/appointments/${id}`, body)
}

export function deleteAppointment(id: number) {
  return api.delete<void>(`/api/v1/appointments/${id}`)
}

/** Bounded notification delivery status for one appointment (no recipient/body). */
export function getAppointmentNotificationDeliveries(appointmentId: number) {
  return api
    .get<{ items: NotificationDeliveryStatus[] }>(
      `/api/v1/users/me/notifications/deliveries?appointment_id=${appointmentId}`,
    )
    .then((data) => data.items)
}
