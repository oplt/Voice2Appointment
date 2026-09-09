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

export function listPriceBooks() {
  return api.get<PriceBook[]>('/api/v1/price-books')
}

export function createPriceBook(body: PriceBookCreate) {
  return api.post<PriceBook>('/api/v1/price-books', body)
}

export function listPrices(priceBookId: number) {
  return api.get<Price[]>(`/api/v1/price-books/${priceBookId}/prices`)
}

export function createPrice(priceBookId: number, body: PriceCreate) {
  return api.post<Price>(`/api/v1/price-books/${priceBookId}/prices`, body)
}
