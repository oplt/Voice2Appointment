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

export type CustomerWrite = {
  name?: string | null
  phone?: string | null
  email?: string | null
  language?: string | null
  consent_preferences?: Record<string, unknown>
  metadata_json?: Record<string, unknown>
}

export function listCustomers(query?: string) {
  const search = new URLSearchParams()
  if (query) search.set('query', query)
  const qs = search.toString()
  return api.get<Customer[]>(`/api/v1/customers${qs ? `?${qs}` : ''}`)
}

export function createCustomer(body: CustomerWrite) {
  return api.post<Customer>('/api/v1/customers', body)
}

export function patchCustomer(customerId: number, body: CustomerWrite) {
  return api.patch<Customer>(`/api/v1/customers/${customerId}`, body)
}
