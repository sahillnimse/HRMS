import { useCallback, useState } from 'react'
import { api, getErrorMessage } from '@/lib/api'
import type {
  ApplicationItem,
  ApplicationStage,
  JobDetail,
  JobItem,
  JobPayload,
  JobStatus,
} from '@/types'

export function useJobs() {
  const [jobs, setJobs] = useState<JobItem[]>([])
  const [jobDetail, setJobDetail] = useState<JobDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchJobs = useCallback(
    async (params?: { status?: JobStatus; department?: string; search?: string }) => {
      setLoading(true)
      setError(null)
      try {
        const res = await api.get<JobItem[]>('/jobs/', { params })
        setJobs(res.data)
        return res.data
      } catch (err) {
        setError(getErrorMessage(err, 'Failed to load jobs'))
        return []
      } finally {
        setLoading(false)
      }
    },
    [],
  )

  const fetchJobDetail = useCallback(async (jobId: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<JobDetail>(`/jobs/${jobId}`)
      setJobDetail(res.data)
      return res.data
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load job'))
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  const createJob = useCallback(async (payload: JobPayload): Promise<JobItem | null> => {
    setError(null)
    try {
      const res = await api.post<JobItem>('/jobs/', payload)
      return res.data
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create job'))
      return null
    }
  }, [])

  const updateJob = useCallback(
    async (jobId: string, payload: Partial<JobPayload>): Promise<JobItem | null> => {
      setError(null)
      try {
        const res = await api.put<JobItem>(`/jobs/${jobId}`, payload)
        return res.data
      } catch (err) {
        setError(getErrorMessage(err, 'Failed to update job'))
        return null
      }
    },
    [],
  )

  const deleteJob = useCallback(async (jobId: string): Promise<boolean> => {
    setError(null)
    try {
      await api.delete(`/jobs/${jobId}`)
      return true
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to delete job'))
      return false
    }
  }, [])

  const addApplication = useCallback(
    async (candidateId: string, jobId: string, stage: ApplicationStage = 'applied') => {
      setError(null)
      try {
        const res = await api.post<ApplicationItem>('/applications/', {
          candidate_id: candidateId,
          job_id: jobId,
          stage,
        })
        return res.data
      } catch (err) {
        setError(getErrorMessage(err, 'Failed to add candidate to job'))
        return null
      }
    },
    [],
  )

  const moveStage = useCallback(
    async (
      applicationId: string,
      stage: ApplicationStage,
      opts?: { rejection_reason?: string; reason?: string },
    ) => {
      setError(null)
      try {
        const res = await api.patch<ApplicationItem>(`/applications/${applicationId}/stage`, {
          stage,
          ...opts,
        })
        return res.data
      } catch (err) {
        setError(getErrorMessage(err, 'Failed to update stage'))
        return null
      }
    },
    [],
  )

  const removeApplication = useCallback(async (applicationId: string): Promise<boolean> => {
    setError(null)
    try {
      await api.delete(`/applications/${applicationId}`)
      return true
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to remove candidate from job'))
      return false
    }
  }, [])

  return {
    jobs,
    jobDetail,
    setJobDetail,
    loading,
    error,
    fetchJobs,
    fetchJobDetail,
    createJob,
    updateJob,
    deleteJob,
    addApplication,
    moveStage,
    removeApplication,
  }
}
