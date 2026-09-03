import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { ApiError } from '../api/client'
import { loginRequest, logoutRequest, meRequest, registerRequest } from '../api/auth'
import type { User } from '../types'

const AUTH_BOOTSTRAP_MS = 12_000

type AuthContextValue = {
  user: User | null
  isAuthenticated: boolean
  isReady: boolean
  authError: string | null
  retryBootstrap: () => void
  login: (email: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

type AuthProviderProps = {
  children: ReactNode
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null)
  const [isReady, setIsReady] = useState(false)
  const [authError, setAuthError] = useState<string | null>(null)
  const [bootTick, setBootTick] = useState(0)

  const clearSession = useCallback(() => {
    setUser(null)
  }, [])

  useEffect(() => {
    let cancelled = false
    setIsReady(false)
    setAuthError(null)

    const timeout = window.setTimeout(() => {
      if (!cancelled) {
        clearSession()
        setAuthError('Sign-in check timed out. Check your connection and retry.')
        setIsReady(true)
      }
    }, AUTH_BOOTSTRAP_MS)

    meRequest()
      .then((nextUser) => {
        if (!cancelled) {
          setUser(nextUser)
          setAuthError(null)
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearSession()
        }
      })
      .finally(() => {
        if (!cancelled) {
          window.clearTimeout(timeout)
          setIsReady(true)
        }
      })

    const onUnauthorized = () => clearSession()
    window.addEventListener('auth:unauthorized', onUnauthorized)
    return () => {
      cancelled = true
      window.clearTimeout(timeout)
      window.removeEventListener('auth:unauthorized', onUnauthorized)
    }
  }, [clearSession, bootTick])

  const retryBootstrap = useCallback(() => {
    setBootTick((n) => n + 1)
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const result = await loginRequest(email, password)
    setUser(result.user)
    setAuthError(null)
  }, [])

  const register = useCallback(async (username: string, email: string, password: string) => {
    const result = await registerRequest(username, email, password)
    setUser(result.user)
    setAuthError(null)
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) {
        // Still clear local session if logout endpoint is unreachable.
      }
    } finally {
      clearSession()
    }
  }, [clearSession])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      isAuthenticated: Boolean(user),
      isReady,
      authError,
      retryBootstrap,
      login,
      register,
      logout,
    }),
    [user, isReady, authError, retryBootstrap, login, register, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
