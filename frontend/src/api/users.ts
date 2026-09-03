import { api } from './client'
import type { UserProfile, UserProfileUpdate } from '../types'

export function getMe() {
  return api.get<UserProfile>('/api/v1/users/me')
}

export function updateMe(body: UserProfileUpdate) {
  return api.patch<UserProfile>('/api/v1/users/me', body)
}
