import axios, { isAxiosError } from 'axios'

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 120000,
})

/** Public URL of an uploaded resume file served by the backend's /files mount. */
export function getFileUrl(storedFilename: string): string {
  const origin = API_BASE_URL.replace(/\/api\/v1\/?$/, '')
  return `${origin}/files/${encodeURIComponent(storedFilename)}`
}

interface ValidationIssue {
  loc?: unknown[]
  msg?: string
}

/** Turn axios / FastAPI errors (string or validation array) into readable text. */
export function getErrorMessage(err: unknown, fallback: string): string {
  if (isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      const message = (detail as ValidationIssue[])
        .map((issue) => {
          const loc = Array.isArray(issue.loc)
            ? issue.loc.filter((part) => part !== 'body').join('.')
            : ''
          return loc ? `${loc}: ${issue.msg ?? 'invalid'}` : issue.msg
        })
        .filter(Boolean)
        .join('; ')
      return message || fallback
    }
    if (err.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
    if (!err.response) return 'Cannot reach the server. Make sure the backend is running.'
    return err.message || fallback
  }
  if (err instanceof Error) return err.message || fallback
  return fallback
}
