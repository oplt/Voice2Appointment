import { api } from './client'
import type { Appointment, AppointmentCreate, AppointmentUpdate } from '../types'

export type AppointmentsListResponse = Appointment[] | { items: Appointment[] }

function normalizeList(data: AppointmentsListResponse): Appointment[] {
  return Array.isArray(data) ? data : (data.items ?? [])
}

export async function listAppointments() {
  const data = await api.get<AppointmentsListResponse>('/api/v1/appointments')
  return normalizeList(data)
}

export function getAppointment(id: number) {
  return api.get<Appointment>(`/api/v1/appointments/${id}`)
}

export function createAppointment(body: AppointmentCreate) {
  return api.post<Appointment>('/api/v1/appointments', body)
}

export function updateAppointment(id: number, body: AppointmentUpdate) {
  return api.patch<Appointment>(`/api/v1/appointments/${id}`, body)
}

export function deleteAppointment(id: number) {
  return api.delete<void>(`/api/v1/appointments/${id}`)
}
