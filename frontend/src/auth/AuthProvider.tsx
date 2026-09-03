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

type AuthContextValue = {
  user: User | null
  isAuthenticated: boolean
  isReady: boolean
  login: (email: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

type AuthProviderProps = {
  children: ReactNode
}

/**
 * Cookie-session auth against FastAPI.
 * HttpOnly cookie is set by the API — nothing sensitive in localStorage.
 */
export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null)
  const [isReady, setIsReady] = useState(false)

  const clearSession = useCallback(() => {
    setUser(null)
  }, [])

  useEffect(() => {
    let cancelled = false
    meRequest()
      .then((nextUser) => {
        if (!cancelled) {
          setUser(nextUser)
        }
      })
      .catch(() => {
        if (!cancelled) {
          clearSession()
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsReady(true)
        }
      })

    const onUnauthorized = () => clearSession()
    window.addEventListener('auth:unauthorized', onUnauthorized)
    return () => {
      cancelled = true
      window.removeEventListener('auth:unauthorized', onUnauthorized)
    }
  }, [clearSession])

  const login = useCallback(async (email: string, password: string) => {
    const result = await loginRequest(email, password)
    setUser(result.user)
  }, [])

  const register = useCallback(async (username: string, email: string, password: string) => {
    const result = await registerRequest(username, email, password)
    setUser(result.user)
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
      login,
      register,
      logout,
    }),
    [user, isReady, login, register, logout],
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
