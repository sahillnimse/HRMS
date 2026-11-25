import { useEffect, useState } from 'react'
import { AlertCircle, Download, ExternalLink, FileText, Loader2 } from 'lucide-react'
import { fetchResumeBlob } from '@/lib/api'
import { Button } from '@/components/ui/Button'

interface ResumePreviewProps {
  resumeFileId: string | null
  originalFilename: string | null
  storedFilename?: string | null
  previewHeightClass?: string
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

export function ResumePreview({
  resumeFileId,
  originalFilename,
  storedFilename,
  previewHeightClass = 'h-72',
}: ResumePreviewProps) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const validFileId = resumeFileId && UUID_RE.test(resumeFileId) ? resumeFileId : null
  const isPdf = (originalFilename ?? storedFilename ?? '').toLowerCase().endsWith('.pdf')

  useEffect(() => {
    if (!validFileId || !isPdf) {
      setBlobUrl(null)
      return
    }
    let active = true
    let createdUrl: string | null = null
    setLoading(true)
    setError(null)

    fetchResumeBlob(validFileId, false)
      .then((blob) => {
        if (!active) return
        createdUrl = URL.createObjectURL(blob)
        setBlobUrl(createdUrl)
      })
      .catch(() => {
        if (active) setError('Could not load authenticated preview.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
      if (createdUrl) URL.revokeObjectURL(createdUrl)
    }
  }, [validFileId, isPdf])

  if (!validFileId) return null

  const handleOpen = async () => {
    try {
      if (blobUrl) {
        window.open(blobUrl, '_blank', 'noopener,noreferrer')
        return
      }
      setDownloading(true)
      const blob = await fetchResumeBlob(validFileId, false)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      setError('Failed to open resume file.')
    } finally {
      setDownloading(false)
    }
  }

  const handleDownload = async () => {
    try {
      setDownloading(true)
      const blob = await fetchResumeBlob(validFileId, true)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = originalFilename || 'resume'
      a.click()
      URL.revokeObjectURL(url)
    } catch {
      setError('Failed to download resume file.')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="rounded-2xl border bg-white p-5 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
            <FileText size={20} />
          </div>
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Source Document
            </p>
            <p className="truncate text-sm font-semibold text-slate-900">
              {originalFilename || 'Uploaded resume'}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Button type="button" variant="outline" size="sm" onClick={handleOpen} disabled={downloading}>
            <ExternalLink size={14} />
            Open
          </Button>
          <Button type="button" variant="soft" size="sm" onClick={handleDownload} loading={downloading}>
            <Download size={14} />
            Download
          </Button>
        </div>
      </div>

      {error && (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          <AlertCircle size={14} />
          {error}
        </div>
      )}

      {isPdf && (
        <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
          {loading ? (
            <div className="flex h-64 items-center justify-center gap-2 text-xs text-slate-500">
              <Loader2 size={15} className="animate-spin text-brand-600" />
              Loading document…
            </div>
          ) : blobUrl ? (
            <iframe
              src={blobUrl}
              title={originalFilename || 'Resume PDF preview'}
              className={`w-full ${previewHeightClass}`}
            />
          ) : null}
        </div>
      )}
    </div>
  )
}
