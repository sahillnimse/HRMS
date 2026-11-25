import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import {
  api,
  getErrorMessage,
  setAccessToken,
  UNAUTHORIZED_EVENT,
} from '@/lib/api'
import type { TokenResponse, User } from '@/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  canWrite: boolean
  isAdmin: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState<boolean>(true)

  const clearClientSession = useCallback(() => {
    setAccessToken(null)
    setUser(null)
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      // Clear local session even if server logout call fails
    } finally {
      clearClientSession()
    }
  }, [clearClientSession])

  useEffect(() => {
    const onUnauthorized = () => clearClientSession()
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [clearClientSession])

  // Restore session silently on mount using the httpOnly refresh cookie
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .post<TokenResponse>('/auth/refresh')
      .then((res) => {
        if (cancelled) return
        setAccessToken(res.data.access_token)
        setUser(res.data.user)
      })
      .catch(() => {
        if (!cancelled) clearClientSession()
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [clearClientSession])

  const login = useCallback(async (email: string, password: string) => {
    try {
      const res = await api.post<TokenResponse>('/auth/login', { email, password })
      setAccessToken(res.data.access_token)
      setUser(res.data.user)
    } catch (err) {
      throw new Error(getErrorMessage(err, 'Invalid email or password'))
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      loading,
      canWrite: user?.role === 'admin' || user?.role === 'recruiter',
      isAdmin: user?.role === 'admin',
      login,
      logout,
    }),
    [user, loading, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
