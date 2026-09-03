import { api } from './client'
import type { User } from '../types'

export type AuthResponse = {
  user: User
}

export type MessageResponse = {
  message: string
}

export function loginRequest(email: string, password: string) {
  return api.post<AuthResponse>('/api/v1/auth/login', { email, password })
}

export function registerRequest(username: string, email: string, password: string) {
  return api.post<AuthResponse>('/api/v1/auth/register', { username, email, password })
}

export function logoutRequest() {
  return api.post<MessageResponse>('/api/v1/auth/logout')
}

export function meRequest() {
  return api.get<User>('/api/v1/auth/me')
}

export function healthRequest() {
  return api.get<{ status: string }>('/api/v1/health')
}
