import { Download, ExternalLink, FileText } from 'lucide-react'
import { getFileUrl } from '@/lib/api'
import { Button } from '@/components/ui/Button'

interface ResumePreviewProps {
  resumeFileId: string | null
  originalFilename: string | null
  storedFilename: string | null
}

export function ResumePreview({
  resumeFileId,
  originalFilename,
  storedFilename,
}: ResumePreviewProps) {
  if (!resumeFileId && !storedFilename) return null

  const downloadUrl = storedFilename ? getFileUrl(storedFilename) : null
  const isPdf = (originalFilename ?? storedFilename ?? '').toLowerCase().endsWith('.pdf')

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
        {downloadUrl && (
          <div className="flex shrink-0 items-center gap-1.5">
            <Button variant="outline" size="sm" asChild>
              <a href={downloadUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink size={14} />
                Open
              </a>
            </Button>
            <Button variant="soft" size="sm" asChild>
              <a href={downloadUrl} download={originalFilename || undefined}>
                <Download size={14} />
                Download
              </a>
            </Button>
          </div>
        )}
      </div>

      {downloadUrl && isPdf && (
        <div className="mt-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-50">
          <iframe
            src={downloadUrl}
            title={originalFilename || 'Resume PDF preview'}
            className="h-72 w-full"
          />
        </div>
      )}
    </div>
  )
}
