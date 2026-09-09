import { api } from './client'

export type Customer = {
  id: number
  name: string | null
  phone: string | null
  email: string | null
  language: string | null
  consent_preferences: Record<string, unknown>
  metadata_json: Record<string, unknown>
}

export type CustomerPage = {
  items: Customer[]
  total: number
  limit: number
  offset: number
}

export type CustomerWrite = {
  name?: string | null
  phone?: string | null
  email?: string | null
  language?: string | null
  consent_preferences?: Record<string, unknown>
  metadata_json?: Record<string, unknown>
}

export function listCustomers(
  params?: { query?: string; limit?: number; offset?: number },
  signal?: AbortSignal,
) {
  const search = new URLSearchParams()
  if (params?.query) search.set('query', params.query)
  if (params?.limit != null) search.set('limit', String(params.limit))
  if (params?.offset != null) search.set('offset', String(params.offset))
  const qs = search.toString()
  return api.get<CustomerPage>(`/api/v1/customers${qs ? `?${qs}` : ''}`, { signal })
}

export function createCustomer(body: CustomerWrite) {
  return api.post<Customer>('/api/v1/customers', body)
}

export function getCustomer(customerId: number) {
  return api.get<Customer>(`/api/v1/customers/${customerId}`)
}

export function patchCustomer(customerId: number, body: CustomerWrite) {
  return api.patch<Customer>(`/api/v1/customers/${customerId}`, body)
}

export type CustomerReservation = {
  id: number
  status: string
  start_datetime: string
  end_datetime: string
  party_size: number
  catalog_item_id: number | null
  appointment_id: number | null
}

export function listCustomerReservations(customerId: number) {
  return api.get<CustomerReservation[]>(`/api/v1/customers/${customerId}/reservations`)
}

export function mergeCustomers(sourceCustomerId: number, targetCustomerId: number) {
  return api.post<Customer>('/api/v1/customers/merge', {
    source_customer_id: sourceCustomerId,
    target_customer_id: targetCustomerId,
  })
}
