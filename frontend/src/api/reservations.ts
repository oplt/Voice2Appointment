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

export type ReservationLineItem = {
  id: number
  catalog_item_id: number | null
  item_name: string
  quantity: number
  unit_price_minor: number
  currency: string
  tax_metadata: Record<string, unknown>
}

export type ReservationDetail = Reservation & {
  line_items: ReservationLineItem[]
  resource_ids: number[]
}

export type ReservationPage = {
  items: Reservation[]
  total: number
  limit: number
  offset: number
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

export type ListReservationsParams = {
  status?: string
  limit?: number
  offset?: number
}

export function listReservations(params: ListReservationsParams | string = {}) {
  const normalized =
    typeof params === 'string' ? { status: params || undefined } : params
  const search = new URLSearchParams()
  if (normalized.status) search.set('status', normalized.status)
  if (normalized.limit != null) search.set('limit', String(normalized.limit))
  if (normalized.offset != null) search.set('offset', String(normalized.offset))
  const qs = search.toString()
  return api.get<ReservationPage>(`/api/v1/reservations${qs ? `?${qs}` : ''}`)
}

export function getReservation(reservationId: number) {
  return api.get<ReservationDetail>(`/api/v1/reservations/${reservationId}`)
}

export function listReservationLineItems(reservationId: number) {
  return api.get<ReservationLineItem[]>(
    `/api/v1/reservations/${reservationId}/line-items`,
  )
}

export function createReservation(body: ReservationCreate) {
  return api.post<Reservation>('/api/v1/reservations', body)
}

export function holdReservation(
  body: ReservationCreate & { hold_ttl_seconds?: number },
) {
  return api.post<Reservation>('/api/v1/reservations/hold', body)
}

export function commitReservation(reservationId: number) {
  return api.post<Reservation>(`/api/v1/reservations/${reservationId}/commit`)
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

export function updateReservationPartySize(
  reservationId: number,
  body: { party_size: number; idempotency_key?: string | null },
) {
  return api.post<Reservation>(`/api/v1/reservations/${reservationId}/party-size`, body)
}

export function changeReservationResources(
  reservationId: number,
  body: { resource_ids: number[]; idempotency_key?: string | null },
) {
  return api.post<Reservation>(`/api/v1/reservations/${reservationId}/resources`, body)
}

export function findReservationAvailability(body: AvailabilityRequest) {
  return api.post<AvailabilityResponse>('/api/v1/availability', body)
}
