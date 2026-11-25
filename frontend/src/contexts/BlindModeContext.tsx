import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

const STORAGE_KEY = 'hrms_blind_screening'

interface BlindModeContextValue {
  blindMode: boolean
  setBlindMode: (enabled: boolean) => void
  toggleBlindMode: () => void
}

const BlindModeContext = createContext<BlindModeContextValue | null>(null)

export function blindCandidateLabel(candidateId?: string | null): string {
  const clean = (candidateId || '').replace(/-/g, '').slice(0, 6).toUpperCase()
  return clean ? `Candidate #${clean}` : 'Anonymous Candidate'
}

export function BlindModeProvider({ children }: { children: ReactNode }) {
  const [blindMode, setBlindModeState] = useState<boolean>(() => {
    try {
      return window.sessionStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  const setBlindMode = useCallback((enabled: boolean) => {
    setBlindModeState(enabled)
    try {
      window.sessionStorage.setItem(STORAGE_KEY, enabled ? 'true' : 'false')
    } catch {
      // Ignore storage errors
    }
  }, [])

  const toggleBlindMode = useCallback(() => {
    setBlindModeState((prev) => {
      const next = !prev
      try {
        window.sessionStorage.setItem(STORAGE_KEY, next ? 'true' : 'false')
      } catch {
        // Ignore storage errors
      }
      return next
    })
  }, [])

  return (
    <BlindModeContext.Provider value={{ blindMode, setBlindMode, toggleBlindMode }}>
      {children}
    </BlindModeContext.Provider>
  )
}

export function useBlindMode(): BlindModeContextValue {
  const ctx = useContext(BlindModeContext)
  if (!ctx) {
    return {
      blindMode: false,
      setBlindMode: () => {},
      toggleBlindMode: () => {},
    }
  }
  return ctx
}
