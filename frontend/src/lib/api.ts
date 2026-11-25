import axios, { isAxiosError } from 'axios'

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || '/api/v1'
const TOKEN_STORAGE_KEY = 'hrms_access_token'
export const UNAUTHORIZED_EVENT = 'hrms:unauthorized'

export function getStoredToken(): string | null {
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

export function setStoredToken(token: string | null): void {
  try {
    if (token) window.localStorage.setItem(TOKEN_STORAGE_KEY, token)
    else window.localStorage.removeItem(TOKEN_STORAGE_KEY)
  } catch {
    // Ignore storage errors in restricted environments
  }
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 120000,
})

api.interceptors.request.use((config) => {
  const token = getStoredToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      isAxiosError(error) &&
      error.response?.status === 401 &&
      !error.config?.url?.includes('/auth/login')
    ) {
      setStoredToken(null)
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
export async function fetchResumeBlob(
  resumeFileId: string,
  download = false,
): Promise<Blob> {
  const response = await api.get<Blob>(`/resumes/${encodeURIComponent(resumeFileId)}/file`, {
    params: download ? { download: true } : undefined,
    responseType: 'blob',
  })
  return response.data
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
