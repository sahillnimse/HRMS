import { useState, useCallback } from 'react'
import { api, getErrorMessage } from '@/lib/api'
import type { ResumeUploadResponse } from '@/types'

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

  const clearUpload = useCallback(() => {
    setLastUpload(null)
    setUploadError(null)
  }, [])

  return {
    uploading,
    uploadError,
    lastUpload,
    uploadResume,
    clearUpload,
  }
}
