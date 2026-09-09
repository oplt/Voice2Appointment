import { api } from './client'

export type PriceBook = {
  id: number
  name: string
  currency: string
  active: boolean
}

export type Price = {
  id: number
  price_book_id: number
  catalog_item_id: number
  location_id: number | null
  amount_minor: number
  currency: string
  channel: string | null
  effective_from: string | null
  effective_until: string | null
  tax_metadata: Record<string, unknown>
}

export type PriceBookCreate = {
  name: string
  currency: string
  active?: boolean
}

export type PriceBookPatch = {
  name?: string
  currency?: string
  active?: boolean
}

export type PriceCreate = {
  catalog_item_id: number
  location_id?: number | null
  amount_minor: number
  currency: string
  channel?: string | null
  effective_from?: string | null
  effective_until?: string | null
  tax_metadata?: Record<string, unknown>
}

export type PricePatch = {
  location_id?: number | null
  amount_minor?: number
  currency?: string
  channel?: string | null
  effective_from?: string | null
  effective_until?: string | null
  tax_metadata?: Record<string, unknown>
}

export type Location = {
  id: number
  name: string
  timezone: string
  address: string | null
  phone: string | null
}

export function listPriceBooks() {
  return api.get<PriceBook[]>('/api/v1/price-books')
}

export function createPriceBook(body: PriceBookCreate) {
  return api.post<PriceBook>('/api/v1/price-books', body)
}

export function patchPriceBook(priceBookId: number, body: PriceBookPatch) {
  return api.patch<PriceBook>(`/api/v1/price-books/${priceBookId}`, body)
}

export function archivePriceBook(priceBookId: number) {
  return api.post<PriceBook>(`/api/v1/price-books/${priceBookId}/archive`)
}

export function listPrices(priceBookId: number) {
  return api.get<Price[]>(`/api/v1/price-books/${priceBookId}/prices`)
}

export function createPrice(priceBookId: number, body: PriceCreate) {
  return api.post<Price>(`/api/v1/price-books/${priceBookId}/prices`, body)
}

export function patchPrice(priceBookId: number, priceId: number, body: PricePatch) {
  return api.patch<Price>(`/api/v1/price-books/${priceBookId}/prices/${priceId}`, body)
}

export function archivePrice(priceBookId: number, priceId: number) {
  return api.post<Price>(`/api/v1/price-books/${priceBookId}/prices/${priceId}/archive`)
}

export function deletePrice(priceBookId: number, priceId: number) {
  return api.delete<void>(`/api/v1/price-books/${priceBookId}/prices/${priceId}`)
}

export function listLocations(signal?: AbortSignal) {
  return api.get<Location[]>('/api/v1/locations', { signal })
}
