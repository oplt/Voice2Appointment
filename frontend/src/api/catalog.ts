import { api } from './client'

export type CatalogKind = 'service' | 'product' | 'addon' | 'package'

export type CatalogCategory = {
  id: number
  name: string
  active: boolean
}

export type CatalogItem = {
  id: number
  name: string
  kind: CatalogKind
  category_id: number | null
  description: string | null
  active: boolean
  bookable: boolean
  sellable: boolean
  duration_minutes: number | null
  buffer_before_minutes: number
  buffer_after_minutes: number
  metadata_json: Record<string, unknown>
  version: number
}

export type CatalogItemPage = {
  items: CatalogItem[]
  total: number
  limit: number
  offset: number
}

export type CatalogItemCreate = {
  name: string
  kind?: CatalogKind
  category_id?: number | null
  description?: string | null
  active?: boolean
  bookable?: boolean
  sellable?: boolean
  duration_minutes?: number | null
  buffer_before_minutes?: number
  buffer_after_minutes?: number
  metadata_json?: Record<string, unknown>
}

export type CatalogItemPatch = Partial<CatalogItemCreate> & {
  expected_version: number
}

export type ListCatalogItemsParams = {
  active?: boolean
  query?: string
  category_id?: number
  kind?: CatalogKind
  limit?: number
  offset?: number
}

export function listCategories() {
  return api.get<CatalogCategory[]>('/api/v1/catalog/categories')
}

export function createCategory(body: { name: string; active?: boolean }) {
  return api.post<CatalogCategory>('/api/v1/catalog/categories', body)
}

export function patchCategory(
  categoryId: number,
  body: { name?: string; active?: boolean },
) {
  return api.patch<CatalogCategory>(`/api/v1/catalog/categories/${categoryId}`, body)
}

export function listCatalogItems(params: ListCatalogItemsParams = {}) {
  const search = new URLSearchParams()
  if (params.active != null) search.set('active', String(params.active))
  if (params.query) search.set('query', params.query)
  if (params.category_id != null) search.set('category_id', String(params.category_id))
  if (params.kind) search.set('kind', params.kind)
  if (params.limit != null) search.set('limit', String(params.limit))
  if (params.offset != null) search.set('offset', String(params.offset))
  const qs = search.toString()
  return api.get<CatalogItemPage>(`/api/v1/catalog/items${qs ? `?${qs}` : ''}`)
}

export function createCatalogItem(body: CatalogItemCreate) {
  return api.post<CatalogItem>('/api/v1/catalog/items', body)
}

export function getCatalogItem(itemId: number) {
  return api.get<CatalogItem>(`/api/v1/catalog/items/${itemId}`)
}

export function patchCatalogItem(itemId: number, body: CatalogItemPatch) {
  return api.patch<CatalogItem>(`/api/v1/catalog/items/${itemId}`, body)
}

export function archiveCatalogItem(itemId: number, expectedVersion: number) {
  return api.post<CatalogItem>(
    `/api/v1/catalog/items/${itemId}/archive?expected_version=${expectedVersion}`,
  )
}

export function bulkActivateCatalogItems(itemIds: number[]) {
  return api.post<CatalogItem[]>('/api/v1/catalog/bulk-activate', { item_ids: itemIds })
}

export function bulkDeactivateCatalogItems(itemIds: number[]) {
  return api.post<CatalogItem[]>('/api/v1/catalog/bulk-deactivate', { item_ids: itemIds })
}
