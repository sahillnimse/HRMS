import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import {
  api,
  getErrorMessage,
  getStoredToken,
  setStoredToken,
  UNAUTHORIZED_EVENT,
} from '@/lib/api'
import type { TokenResponse, User } from '@/types'

interface AuthContextValue {
  user: User | null
  token: string | null
  loading: boolean
  canWrite: boolean
  isAdmin: boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(() => getStoredToken())
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState<boolean>(() => Boolean(getStoredToken()))

  const logout = useCallback(() => {
    setStoredToken(null)
    setToken(null)
    setUser(null)
  }, [])

  useEffect(() => {
    const onUnauthorized = () => logout()
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
  }, [logout])

  useEffect(() => {
    if (!token) {
      setUser(null)
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    api
      .get<User>('/auth/me')
      .then((res) => {
        if (!cancelled) setUser(res.data)
      })
      .catch(() => {
        if (!cancelled) logout()
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [token, logout])

  const login = useCallback(async (email: string, password: string) => {
    try {
      const res = await api.post<TokenResponse>('/auth/login', { email, password })
      setStoredToken(res.data.access_token)
      setToken(res.data.access_token)
      setUser(res.data.user)
    } catch (err) {
      throw new Error(getErrorMessage(err, 'Invalid email or password'))
    }
  }, [])

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      loading,
      canWrite: user?.role === 'admin' || user?.role === 'recruiter',
      isAdmin: user?.role === 'admin',
      login,
      logout,
    }),
    [user, token, loading, login, logout],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
