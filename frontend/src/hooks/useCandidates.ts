import { useState, useCallback } from 'react'
import { api, getErrorMessage } from '@/lib/api'
import type {
  CandidateFilters,
  CandidateListItem,
  CandidateResponse,
  CandidateStats,
  CandidateUpdate,
  PaginatedCandidates,
} from '@/types'

export function useCandidates() {
  const [candidates, setCandidates] = useState<CandidateListItem[]>([])
  const [stats, setStats] = useState<CandidateStats | null>(null)
  const [pagination, setPagination] = useState({
    total: 0,
    page: 1,
    page_size: 20,
    pages: 0,
  })
  const [loading, setLoading] = useState(false)
  const [statsLoading, setStatsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<CandidateResponse | null>(null)

  const fetchCandidates = useCallback(async (params?: CandidateFilters) => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.get<PaginatedCandidates>('/candidates/', { params })
      setCandidates(response.data.items)
      setPagination({
        total: response.data.total,
        page: response.data.page,
        page_size: response.data.page_size,
        pages: response.data.pages,
      })
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load candidates'))
    } finally {
      setLoading(false)
    }
  }, [])

  const fetchStats = useCallback(async () => {
    setStatsLoading(true)
    try {
      const response = await api.get<CandidateStats>('/candidates/stats')
      setStats(response.data)
      return response.data
    } catch {
      return null
    } finally {
      setStatsLoading(false)
    }
  }, [])

  const createCandidate = useCallback(
    async (payload: CandidateUpdate & { resume_file_id?: string | null }): Promise<CandidateResponse | null> => {
      setLoading(true)
      setError(null)
      try {
        const response = await api.post<CandidateResponse>('/candidates/', payload)
        setSelected(response.data)
        return response.data
      } catch (err) {
        setError(getErrorMessage(err, 'Failed to save candidate'))
        return null
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  const updateCandidate = useCallback(
    async (id: string, payload: CandidateUpdate): Promise<CandidateResponse | null> => {
      setLoading(true)
      setError(null)
      try {
        const response = await api.put<CandidateResponse>(`/candidates/${id}`, payload)
        setSelected(response.data)
        return response.data
      } catch (err) {
        setError(getErrorMessage(err, 'Failed to update candidate'))
        return null
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  const getCandidate = useCallback(async (id: string): Promise<CandidateResponse | null> => {
    setLoading(true)
    setError(null)
    try {
      const response = await api.get<CandidateResponse>(`/candidates/${id}`)
      setSelected(response.data)
      return response.data
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load candidate'))
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const deleteCandidate = useCallback(async (id: string): Promise<boolean> => {
    setLoading(true)
    setError(null)
    try {
      await api.delete(`/candidates/${id}`)
      return true
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to delete candidate'))
      return false
    } finally {
      setLoading(false)
    }
  }, [])

  return {
    candidates,
    stats,
    pagination,
    loading,
    statsLoading,
    error,
    selected,
    fetchCandidates,
    fetchStats,
    createCandidate,
    updateCandidate,
    getCandidate,
    deleteCandidate,
    setSelected,
  }
}
