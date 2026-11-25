import { useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { AlertCircle, CloudUpload, FileText, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

interface ResumeDropzoneProps {
  onFileAccept?: (file: File) => void
  onFilesAccept?: (files: File[]) => void
  multiple?: boolean
  maxFiles?: number
  accepting: boolean
}

export function ResumeDropzone({
  onFileAccept,
  onFilesAccept,
  multiple = false,
  maxFiles = 25,
  accepting,
}: ResumeDropzoneProps) {
  const [rejectMsg, setRejectMsg] = useState<string | null>(null)

  const { getRootProps, getInputProps, isDragActive, isDragReject } = useDropzone({
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
    },
    maxSize: 10 * 1024 * 1024,
    multiple,
    maxFiles: multiple ? maxFiles : 1,
    disabled: accepting,
    onDropAccepted: (files) => {
      setRejectMsg(null)
      if (files.length === 0) return
      if (onFilesAccept) {
        onFilesAccept(files)
      } else if (onFileAccept && files[0]) {
        onFileAccept(files[0])
      }
    },
    onDropRejected: (rejections) => {
      const code = rejections[0]?.errors[0]?.code
      if (code === 'file-too-large') {
        setRejectMsg('One or more files exceed the 10 MB limit.')
      } else if (code === 'too-many-files') {
        setRejectMsg(`You can upload up to ${maxFiles} resumes per batch.`)
      } else {
        setRejectMsg('Unsupported file format. Please upload PDF (.pdf) or Word (.docx) resumes.')
      }
    },
  })

  return (
    <div className="space-y-3">
      <div
        {...getRootProps()}
        className={cn(
          'group relative cursor-pointer overflow-hidden rounded-2xl border-2 border-dashed p-10 text-center transition duration-200',
          accepting && 'pointer-events-none opacity-60',
          isDragReject
            ? 'border-red-400 bg-red-50/70'
            : isDragActive
              ? 'border-brand-500 bg-brand-50/70 ring-4 ring-brand-100'
              : 'border-slate-300 bg-slate-50/60 bg-dots hover:border-brand-400 hover:bg-brand-50/30',
        )}
      >
        <input {...getInputProps()} />

        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-white shadow-md ring-1 ring-slate-200/80 transition duration-200 group-hover:-translate-y-0.5 group-hover:ring-brand-200">
          {isDragReject ? (
            <AlertCircle size={30} className="text-red-500" />
          ) : isDragActive ? (
            <Sparkles size={30} className="text-brand-600" />
          ) : (
            <CloudUpload size={30} className="text-brand-600" />
          )}
        </div>

        <h3 className="mt-5 text-base font-semibold text-slate-900">
          {isDragActive
            ? multiple
              ? 'Release to queue these resumes'
              : 'Release to analyze this resume'
            : multiple
              ? 'Drop one or multiple resumes here'
              : 'Drop candidate resume or CV here'}
        </h3>
        <p className="mx-auto mt-1.5 max-w-sm text-sm text-slate-500">
          Automatically extracts contact details, career timeline, skills, and falls back to OCR
          for scanned PDFs.
        </p>

        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          <Button type="button" variant="outline" size="sm" className="bg-white">
            <FileText size={15} />
            {multiple ? 'Browse files (single or bulk)' : 'Browse files'}
          </Button>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-center gap-2 text-xs text-slate-400">
          <span className="rounded-md border border-slate-200 bg-white px-2 py-0.5 font-medium text-slate-600">
            PDF (incl. scanned OCR)
          </span>
          <span className="rounded-md border border-slate-200 bg-white px-2 py-0.5 font-medium text-slate-600">
            DOCX
          </span>
          <span>· Up to 10 MB each{multiple ? ` · Max ${maxFiles} files` : ''}</span>
        </div>
      </div>

      {rejectMsg && (
        <div className="flex items-center gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-xs font-medium text-red-700">
          <AlertCircle size={15} className="shrink-0" />
          {rejectMsg}
        </div>
      )}
    </div>
  )
}
