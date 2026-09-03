import { api } from './client'
import type {
  BookingPolicy,
  ProductPrefs,
  SetupReadiness,
  UserProfile,
  UserProfileUpdate,
} from '../types'

export function getMe() {
  return api.get<UserProfile>('/api/v1/users/me')
}

export function updateMe(body: UserProfileUpdate) {
  return api.patch<UserProfile>('/api/v1/users/me', body)
}

export function getBookingPolicy() {
  return api.get<BookingPolicy>('/api/v1/users/me/booking-policy')
}

export function putBookingPolicy(body: BookingPolicy) {
  return api.put<BookingPolicy>('/api/v1/users/me/booking-policy', body)
}

export function getProductPrefs() {
  return api.get<ProductPrefs>('/api/v1/users/me/product-prefs')
}

export function putProductPrefs(body: ProductPrefs) {
  return api.put<ProductPrefs>('/api/v1/users/me/product-prefs', body)
}

export function getSetupReadiness() {
  return api.get<SetupReadiness>('/api/v1/users/me/readiness')
}
