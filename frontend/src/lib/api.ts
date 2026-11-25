import axios, { isAxiosError, type InternalAxiosRequestConfig } from 'axios'

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || '/api/v1'
export const UNAUTHORIZED_EVENT = 'hrms:unauthorized'

// Short-lived access token lives ONLY in JS memory (never localStorage) to prevent XSS theft.
// Long-lived session persistence is handled by the server's httpOnly refresh cookie.
let inMemoryAccessToken: string | null = null

export function getAccessToken(): string | null {
  return inMemoryAccessToken
}

export function setAccessToken(token: string | null): void {
  inMemoryAccessToken = token
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 120000,
})

// Single-flight refresh promise so concurrent 401s trigger only one /auth/refresh rotation
let refreshPromise: Promise<string | null> | null = null

export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post<{ access_token: string }>(
        `${API_BASE_URL}/auth/refresh`,
        {},
        { withCredentials: true, timeout: 15000 },
      )
      .then((res) => {
        setAccessToken(res.data.access_token)
        return res.data.access_token
      })
      .catch(() => {
        setAccessToken(null)
        return null
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

api.interceptors.request.use((config) => {
  if (inMemoryAccessToken) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${inMemoryAccessToken}`
  }
  return config
})

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (!isAxiosError(error) || !error.config) {
      return Promise.reject(error)
    }

    const original = error.config as RetryableConfig
    const url = original.url || ''
    const isAuthRoute =
      url.includes('/auth/login') || url.includes('/auth/refresh') || url.includes('/auth/logout')

    if (error.response?.status === 401 && !isAuthRoute && !original._retried) {
      original._retried = true
      const nextToken = await refreshAccessToken()
      if (nextToken) {
        original.headers = original.headers ?? {}
        original.headers.Authorization = `Bearer ${nextToken}`
        return api(original)
      }
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }

    return Promise.reject(error)
  },
)

/** Authenticated API path for streaming a resume file through the storage layer. */
export function getFileUrl(resumeFileId: string, download = false): string {
  const query = download ? '?download=true' : ''
  return `${API_BASE_URL}/resumes/${encodeURIComponent(resumeFileId)}/file${query}`
}

/** Fetch a resume file via authenticated Axios request and return a Blob. */
export async function fetchResumeBlob(resumeFileId: string, download = false): Promise<Blob> {
  const response = await api.get<Blob>(`/resumes/${encodeURIComponent(resumeFileId)}/file`, {
    params: download ? { download: true } : undefined,
    responseType: 'blob',
  })
  return response.data
}

/** Download an authenticated binary file (PDF / XLSX) as a browser attachment. */
export async function downloadBlobFile(
  path: string,
  params: Record<string, unknown> | undefined,
  fallbackFilename: string,
): Promise<void> {
  const response = await api.get<Blob>(path, {
    params,
    responseType: 'blob',
  })
  const disp = String(response.headers?.['content-disposition'] || '')
  const match = disp.match(/filename="?([^"]+)"?/i)
  const filename = match?.[1] || fallbackFilename
  const url = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000)
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
