/** Allow only same-origin relative paths after login (no open redirects). */
export function safeNextPath(value: unknown, fallback = '/dashboard'): string {
  if (typeof value !== 'string') {
    return fallback
  }
  const candidate = value.trim()
  if (
    !candidate.startsWith('/') ||
    candidate.startsWith('//') ||
    candidate.includes('\\') ||
    candidate.includes('://')
  ) {
    return fallback
  }
  try {
    const url = new URL(candidate, window.location.origin)
    if (url.origin !== window.location.origin) {
      return fallback
    }
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return fallback
  }
}
