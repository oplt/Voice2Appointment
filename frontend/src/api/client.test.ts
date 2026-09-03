import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ApiError, apiRequest, ensureCsrf } from './client'

// Stub fetch globally.
const fetchSpy = vi.fn()
vi.stubGlobal('fetch', fetchSpy)

function jsonResponse(status: number, body: unknown, headers?: Record<string, string>) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json', ...headers },
  })
}

beforeEach(() => {
  fetchSpy.mockReset()
  // Clear any cookie left over.
  document.cookie = 'csrf_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT'
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('apiRequest', () => {
  it('returns parsed JSON on success', async () => {
    fetchSpy.mockResolvedValueOnce(jsonResponse(200, { ok: true }))
    const data = await apiRequest<{ ok: boolean }>('/api/test')
    expect(data).toEqual({ ok: true })
  })

  it('throws ApiError on 4xx', async () => {
    fetchSpy.mockResolvedValueOnce(
      jsonResponse(422, { detail: 'Validation failed' }),
    )
    await expect(apiRequest('/api/test')).rejects.toThrow(ApiError)
    try {
      fetchSpy.mockResolvedValueOnce(
        jsonResponse(422, { detail: 'Validation failed' }),
      )
      await apiRequest('/api/test')
    } catch (e) {
      expect(e).toBeInstanceOf(ApiError)
      expect((e as ApiError).status).toBe(422)
      expect((e as ApiError).message).toBe('Validation failed')
    }
  })

  it('dispatches auth:unauthorized on 401', async () => {
    const handler = vi.fn()
    window.addEventListener('auth:unauthorized', handler)
    fetchSpy.mockResolvedValueOnce(jsonResponse(401, { detail: 'Not authenticated' }))
    await expect(apiRequest('/api/test')).rejects.toThrow(ApiError)
    expect(handler).toHaveBeenCalledTimes(1)
    window.removeEventListener('auth:unauthorized', handler)
  })

  it('handles 204 No Content', async () => {
    document.cookie = 'csrf_token=test_csrf'
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 204 }))
    const data = await apiRequest('/api/delete', { method: 'DELETE' })
    expect(data).toBeNull()
  })

  it('attaches CSRF header on POST', async () => {
    // Seed the csrf cookie.
    document.cookie = 'csrf_token=test_csrf_value'
    fetchSpy.mockResolvedValueOnce(jsonResponse(200, { ok: true }))
    await apiRequest('/api/test', { method: 'POST', body: { a: 1 } })
    const headers = fetchSpy.mock.calls[0][1].headers
    expect(headers['X-CSRF-Token']).toBe('test_csrf_value')
  })
})

describe('ensureCsrf', () => {
  it('returns existing cookie without fetch', async () => {
    document.cookie = 'csrf_token=existing'
    const token = await ensureCsrf()
    expect(token).toBe('existing')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  it('fetches csrf endpoint when cookie missing', async () => {
    fetchSpy.mockResolvedValueOnce(new Response(null, { status: 200 }))
    await ensureCsrf()
    expect(fetchSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/auth/csrf'),
      expect.any(Object),
    )
  })
})
