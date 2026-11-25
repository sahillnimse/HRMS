import { useState, useCallback } from 'react'
import { api, getErrorMessage } from '@/lib/api'
import type { BulkUploadResponse, ParseJobItem, ResumeUploadResponse } from '@/types'

export function useResumes() {
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [lastUpload, setLastUpload] = useState<ResumeUploadResponse | null>(null)

  const uploadResume = useCallback(async (file: File): Promise<ResumeUploadResponse | null> => {
    setUploading(true)
    setUploadError(null)

    const formData = new FormData()
    formData.append('file', file)

    try {
      const response = await api.post<ResumeUploadResponse>('/resumes/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      setLastUpload(response.data)
      return response.data
    } catch (err) {
      setUploadError(getErrorMessage(err, 'Resume parsing failed. Please try again.'))
      return null
    } finally {
      setUploading(false)
    }
  }, [])

  const bulkUploadResumes = useCallback(async (files: File[]): Promise<BulkUploadResponse | null> => {
    setUploading(true)
    setUploadError(null)

    const formData = new FormData()
    files.forEach((f) => formData.append('files', f))

    try {
      const response = await api.post<BulkUploadResponse>('/resumes/bulk-upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return response.data
    } catch (err) {
      setUploadError(getErrorMessage(err, 'Bulk upload failed. Please try again.'))
      return null
    } finally {
      setUploading(false)
    }
  }, [])

  const fetchParseJobs = useCallback(async (batchId?: string): Promise<ParseJobItem[]> => {
    try {
      const response = await api.get<ParseJobItem[]>('/resumes/parse-jobs', {
        params: batchId ? { batch_id: batchId } : undefined,
      })
      return response.data
    } catch {
      return []
    }
  }, [])

  const deletePendingResume = useCallback(async (resumeFileId: string): Promise<boolean> => {
    try {
      await api.delete(`/resumes/${encodeURIComponent(resumeFileId)}`)
      return true
    } catch (err) {
      setUploadError(getErrorMessage(err, 'Failed to delete pending resume'))
      return false
    }
  }, [])

  const clearUpload = useCallback(() => {
    setLastUpload(null)
    setUploadError(null)
  }, [])

  return {
    uploading,
    uploadError,
    lastUpload,
    uploadResume,
    bulkUploadResumes,
    fetchParseJobs,
    deletePendingResume,
    clearUpload,
  }
}
