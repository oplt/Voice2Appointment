import type { ApiErrorBody } from '../types'

/** Empty string uses same-origin / Vite proxy in development. */
const DEFAULT_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

const CSRF_COOKIE = 'csrf_token'
const CSRF_HEADER = 'X-CSRF-Token'
const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export class ApiError extends Error {
  status: number
  body: ApiErrorBody | null

  constructor(status: number, message: string, body: ApiErrorBody | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown
  token?: string | null
  skipAuth?: boolean
}

function formatErrorMessage(body: ApiErrorBody | null, status: number): string {
  if (!body) {
    return `Request failed (${status})`
  }
  if (typeof body.message === 'string' && body.message) {
    return body.message
  }
  if (typeof body.detail === 'string' && body.detail) {
    return body.detail
  }
  if (
    body.detail &&
    typeof body.detail === 'object' &&
    !Array.isArray(body.detail) &&
    typeof (body.detail as { message?: string }).message === 'string'
  ) {
    return (body.detail as { message: string }).message
  }
  if (Array.isArray(body.detail) && body.detail.length > 0) {
    return body.detail
      .map((item) => (typeof item === 'string' ? item : item.msg))
      .filter(Boolean)
      .join(', ')
  }
  return `Request failed (${status})`
}

async function parseBody(response: Response): Promise<unknown> {
  if (response.status === 204) {
    return null
  }
  const contentType = response.headers.get('content-type') ?? ''
  if (contentType.includes('application/json')) {
    return response.json()
  }
  const text = await response.text()
  return text || null
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') {
    return null
  }
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

let csrfBootstrap: Promise<void> | null = null

/** Ensure the double-submit CSRF cookie exists before mutating requests. */
export async function ensureCsrf(): Promise<string | null> {
  const existing = readCookie(CSRF_COOKIE)
  if (existing) {
    return existing
  }
  if (!csrfBootstrap) {
    csrfBootstrap = fetch(`${DEFAULT_BASE_URL}/api/v1/auth/csrf`, {
      method: 'GET',
      credentials: 'include',
      headers: { Accept: 'application/json' },
    })
      .then(() => undefined)
      .finally(() => {
        csrfBootstrap = null
      })
  }
  await csrfBootstrap
  return readCookie(CSRF_COOKIE)
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, token, skipAuth: _skipAuth, headers, ...rest } = options
  const method = (rest.method ?? 'GET').toUpperCase()

  const requestHeaders: Record<string, string> = {
    Accept: 'application/json',
    ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(headers as Record<string, string> | undefined),
  }

  if (MUTATING.has(method)) {
    const csrf = await ensureCsrf()
    if (csrf) {
      requestHeaders[CSRF_HEADER] = csrf
    }
  }

  const response = await fetch(`${DEFAULT_BASE_URL}${path}`, {
    ...rest,
    method,
    credentials: 'include',
    headers: requestHeaders,
    body: body === undefined ? undefined : JSON.stringify(body),
  })

  const parsed = (await parseBody(response)) as ApiErrorBody | T

  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent('auth:unauthorized'))
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      formatErrorMessage(parsed as ApiErrorBody, response.status),
      parsed as ApiErrorBody,
    )
  }

  return parsed as T
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PUT', body }),
  patch: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'PATCH', body }),
  delete: <T>(path: string, options?: RequestOptions) =>
    apiRequest<T>(path, { ...options, method: 'DELETE' }),
}
