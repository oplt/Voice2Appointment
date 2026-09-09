import { api } from './client'

export type Reservation = {
  id: number
  location_id: number | null
  customer_id: number | null
  catalog_item_id: number | null
  appointment_id: number | null
  scheduling_mode: string
  status: string
  start_datetime: string
  end_datetime: string
  party_size: number
  hold_expires_at: string | null
  provider_sync_status: string
  allocation_json: Record<string, unknown>
}

export type ReservationCreate = {
  catalog_item_id: number
  start_datetime: string
  end_datetime?: string | null
  location_id?: number | null
  customer_id?: number | null
  party_size?: number
  preferred_resource_ids?: number[]
  required_capabilities?: string[]
  price_book_id?: number | null
  channel?: string | null
  scheduling_mode?: 'single_resource' | 'multi_resource' | 'capacity' | null
  idempotency_key?: string | null
}

export type AvailabilityRequest = {
  catalog_item_id: number
  start_date: string
  end_date?: string | null
  location_id?: number | null
  party_size?: number
  preferred_resource_ids?: number[]
  required_capabilities?: string[]
  price_book_id?: number | null
  channel?: string | null
  slot_step_minutes?: number
  scheduling_mode?: 'single_resource' | 'multi_resource' | 'capacity' | null
}

export type AvailabilitySlot = {
  start_datetime: string
  end_datetime: string
  scheduling_mode: string
  allocations: Record<string, unknown>[]
  price_estimate: Record<string, unknown> | null
  constraints: unknown
}

export type AvailabilityResponse = {
  slots: AvailabilitySlot[]
  constraints: unknown
}

export function listReservations(status?: string) {
  const search = new URLSearchParams()
  if (status) search.set('status', status)
  const qs = search.toString()
  return api.get<Reservation[]>(`/api/v1/reservations${qs ? `?${qs}` : ''}`)
}

export function createReservation(body: ReservationCreate) {
  return api.post<Reservation>('/api/v1/reservations', body)
}

export function cancelReservation(
  reservationId: number,
  body: { reason?: string | null; idempotency_key?: string | null } = {},
) {
  return api.post<Reservation>(`/api/v1/reservations/${reservationId}/cancel`, body)
}

export function rescheduleReservation(
  reservationId: number,
  body: {
    start_datetime: string
    end_datetime?: string | null
    catalog_item_id?: number | null
    party_size?: number | null
    price_book_id?: number | null
    channel?: string | null
    preferred_resource_ids?: number[]
    idempotency_key?: string | null
  },
) {
  return api.post<Reservation>(`/api/v1/reservations/${reservationId}/reschedule`, body)
}

export function findReservationAvailability(body: AvailabilityRequest) {
  return api.post<AvailabilityResponse>('/api/v1/availability', body)
}
