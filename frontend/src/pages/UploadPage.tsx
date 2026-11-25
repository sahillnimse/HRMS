import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Clock,
  FileText,
  Layers,
  Loader2,
  Network,
  ScanText,
  ShieldCheck,
  UserCheck,
  X,
} from 'lucide-react'
import { useResumes } from '@/hooks/useResumes'
import { useCandidates } from '@/hooks/useCandidates'
import { useAddToast } from '@/components/ui/Toast'
import { normalizeProfile, toCandidatePayload, validateProfile } from '@/lib/profile'
import type { ParseJobItem, ResumeUploadResponse } from '@/types'
import { PageHeader } from '@/components/layout/PageHeader'
import { Stepper } from '@/components/ui/Stepper'
import { ResumeDropzone } from '@/components/ResumeDropzone'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/lib/utils'

const PARSE_STAGES = [
  'Extracting text and layout (with OCR fallback for scanned PDFs)',
  'Identifying contact info, career timeline & skills',
  'Generating interactive candidate network graph',
  'Checking database for duplicate candidates',
]

const PENDING_CACHE_KEY = 'hrms_pending_uploads'

function cachePendingUpload(upload: ResumeUploadResponse) {
  try {
    const raw = window.sessionStorage.getItem(PENDING_CACHE_KEY)
    const map = raw ? (JSON.parse(raw) as Record<string, ResumeUploadResponse>) : {}
    map[upload.resume_file_id] = upload
    window.sessionStorage.setItem(PENDING_CACHE_KEY, JSON.stringify(map))
    window.sessionStorage.setItem('hrms_last_upload_id', upload.resume_file_id)
  } catch {
    // Ignore storage quota errors
  }
}

function jobToUploadResponse(job: ParseJobItem): ResumeUploadResponse | null {
  if (job.status !== 'done' || !job.resume_file_id || !job.result_json) return null
  return {
    resume_file_id: job.resume_file_id,
    parsed_data: job.result_json,
    duplicate: job.duplicate_json ?? {
      is_duplicate: false,
      candidate_id: null,
      matched_field: null,
      matches: [],
    },
    ocr_used: job.ocr_used,
    message: `Parsed ${job.original_filename}`,
  }
}

export default function UploadPage() {
  const navigate = useNavigate()
  const addToast = useAddToast()
  const { uploading, uploadError, uploadResume, bulkUploadResumes, fetchParseJobs } = useResumes()
  const { createCandidate, loading: autoSaving } = useCandidates()

  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [autoSave, setAutoSave] = useState(false)
  const [stageIdx, setStageIdx] = useState(0)

  // Bulk batch polling state
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null)
  const [batchJobs, setBatchJobs] = useState<ParseJobItem[]>([])

  const isBulkSelection = selectedFiles.length > 1
  const busy = uploading || autoSaving

  useEffect(() => {
    if (!uploading || isBulkSelection) {
      setStageIdx(0)
      return
    }
    const interval = window.setInterval(() => {
      setStageIdx((prev) => (prev < PARSE_STAGES.length - 1 ? prev + 1 : prev))
    }, 1700)
    return () => window.clearInterval(interval)
  }, [uploading, isBulkSelection])

  // Poll bulk parse jobs every 1.5s until every job is done or failed
  const hasRunningJobs = useMemo(
    () => batchJobs.some((j) => j.status === 'queued' || j.status === 'processing'),
    [batchJobs],
  )

  useEffect(() => {
    if (!activeBatchId || !hasRunningJobs) return
    const timer = window.setInterval(() => {
      void fetchParseJobs(activeBatchId).then((jobs) => {
        if (jobs.length > 0) setBatchJobs(jobs)
      })
    }, 1500)
    return () => window.clearInterval(timer)
  }, [activeBatchId, hasRunningJobs, fetchParseJobs])

  const completedUploads = useMemo(
    () => batchJobs.map(jobToUploadResponse).filter((u): u is ResumeUploadResponse => u !== null),
    [batchJobs],
  )

  const handleFilesAccepted = (files: File[]) => {
    setSelectedFiles((prev) => {
      const existingKeys = new Set(prev.map((f) => `${f.name}-${f.size}`))
      const merged = [...prev]
      for (const f of files) {
        const k = `${f.name}-${f.size}`
        if (!existingKeys.has(k) && merged.length < 25) {
          existingKeys.add(k)
          merged.push(f)
        }
      }
      return merged
    })
  }

  const removeFileAt = (idx: number) => {
    setSelectedFiles((prev) => prev.filter((_, i) => i !== idx))
  }

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return

    // Single-file fast interactive path (preserves existing Phase 0-2 UX)
    if (selectedFiles.length === 1) {
      const result = await uploadResume(selectedFiles[0])
      if (!result) return

      cachePendingUpload(result)

      if (autoSave && !result.duplicate.is_duplicate) {
        const normalized = normalizeProfile(result.parsed_data)
        if (Object.keys(validateProfile(normalized)).length === 0) {
          const saved = await createCandidate({
            resume_file_id: result.resume_file_id,
            ...toCandidatePayload(normalized),
          })
          if (saved) {
            addToast(`${saved.full_name} parsed and saved with CV attached`, 'success')
            navigate(`/candidates/${saved.id}`)
            return
          }
        }
      }

      navigate('/review', { state: { upload: result } })
      return
    }

    // Multi-file bulk queue path (Phase 3)
    const batch = await bulkUploadResumes(selectedFiles)
    if (!batch) return
    setActiveBatchId(batch.batch_id)
    setBatchJobs(batch.jobs)
    setSelectedFiles([])
    addToast(batch.message, 'info')
  }

  const openReviewQueue = (startUpload?: ResumeUploadResponse) => {
    if (completedUploads.length === 0) return
    completedUploads.forEach(cachePendingUpload)
    const ordered = startUpload
      ? [startUpload, ...completedUploads.filter((u) => u.resume_file_id !== startUpload.resume_file_id)]
      : completedUploads
    navigate('/review', {
      state: {
        upload: ordered[0],
        queue: ordered,
      },
    })
  }

  const doneCount = batchJobs.filter((j) => j.status === 'done').length
  const failedCount = batchJobs.filter((j) => j.status === 'failed').length

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="AI Ingestion Pipeline"
        title="Upload & Parse Resumes"
        description="Drop one resume for instant review or up to 25 PDF/DOCX resumes for background bulk parsing with automatic scanned-PDF OCR."
        actions={<Stepper current={uploading ? 1 : 0} />}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left 7 Cols: Dropzone + File List / Bulk Progress */}
        <div className="space-y-5 lg:col-span-7">
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between gap-2">
                <CardTitle>Select Candidate CVs</CardTitle>
                {selectedFiles.length > 1 && (
                  <Badge variant="brand">
                    <Layers size={11} />
                    Bulk mode · {selectedFiles.length} files
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <ResumeDropzone
                multiple
                maxFiles={25}
                onFilesAccept={handleFilesAccepted}
                accepting={uploading}
              />

              {selectedFiles.length > 0 && !uploading && (
                <div className="space-y-2 animate-fade-in">
                  <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>
                      {selectedFiles.length} file{selectedFiles.length === 1 ? '' : 's'} queued for
                      upload
                    </span>
                    <button
                      type="button"
                      onClick={() => setSelectedFiles([])}
                      className="font-medium text-slate-500 hover:text-slate-800"
                    >
                      Clear all
                    </button>
                  </div>
                  <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
                    {selectedFiles.map((file, idx) => (
                      <div
                        key={`${file.name}-${file.size}-${idx}`}
                        className="flex items-center gap-3 rounded-xl border border-brand-200 bg-brand-50/40 px-3.5 py-2.5"
                      >
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-white text-brand-600 shadow-sm ring-1 ring-brand-100">
                          <FileText size={17} />
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-semibold text-slate-900">
                            {file.name}
                          </p>
                          <p className="text-xs text-slate-500">
                            {(file.size / 1024 / 1024).toFixed(2)} MB
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => removeFileAt(idx)}
                          className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white hover:text-slate-700"
                          aria-label={`Remove ${file.name}`}
                        >
                          <X size={15} />
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {uploading && !isBulkSelection && (
                <div className="rounded-2xl border border-brand-200 bg-gradient-to-br from-brand-50/70 to-violet-50/50 p-5 animate-fade-in">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white shadow-glow">
                      <Loader2 size={18} className="animate-spin" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">
                        Analyzing {selectedFiles[0]?.name}
                      </p>
                      <p className="text-xs text-slate-500">
                        Building structured dossier and interactive knowledge graph…
                      </p>
                    </div>
                  </div>

                  <ul className="mt-4 space-y-2.5">
                    {PARSE_STAGES.map((stage, i) => {
                      const done = i < stageIdx
                      const active = i === stageIdx
                      return (
                        <li key={stage} className="flex items-center gap-2.5 text-xs">
                          {done ? (
                            <CheckCircle2 size={15} className="shrink-0 text-emerald-600" />
                          ) : active ? (
                            <Loader2 size={15} className="shrink-0 animate-spin text-brand-600" />
                          ) : (
                            <span className="h-3.5 w-3.5 shrink-0 rounded-full border border-slate-300 bg-white" />
                          )}
                          <span
                            className={cn(
                              done
                                ? 'font-medium text-emerald-700'
                                : active
                                  ? 'font-semibold text-brand-900'
                                  : 'text-slate-400',
                            )}
                          >
                            {stage}
                          </span>
                        </li>
                      )
                    })}
                  </ul>
                </div>
              )}

              {uploadError && (
                <div className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                  <AlertTriangle size={18} className="mt-0.5 shrink-0 text-red-600" />
                  <div>
                    <p className="font-semibold">Upload failed</p>
                    <p className="mt-0.5 text-xs leading-5 text-red-700">{uploadError}</p>
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
                {!isBulkSelection ? (
                  <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-slate-600">
                    <input
                      type="checkbox"
                      checked={autoSave}
                      onChange={(e) => setAutoSave(e.target.checked)}
                      disabled={busy}
                      className="h-4 w-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
                    />
                    Auto-save candidate to directory if no duplicate is found
                  </label>
                ) : (
                  <span className="text-xs text-slate-500">
                    Files parse in the background; review every candidate before saving.
                  </span>
                )}

                <div className="flex items-center justify-end gap-3">
                  <Button variant="outline" onClick={() => navigate('/candidates')} disabled={busy}>
                    Cancel
                  </Button>
                  <Button
                    size="lg"
                    onClick={() => void handleUpload()}
                    disabled={selectedFiles.length === 0 || busy}
                    loading={busy}
                    className="shadow-glow"
                  >
                    {autoSaving
                      ? 'Saving Profile…'
                      : uploading
                        ? isBulkSelection
                          ? 'Queueing Batch…'
                          : 'Analyzing Resume…'
                        : isBulkSelection
                          ? `Queue ${selectedFiles.length} Resumes`
                          : 'Parse & Generate Network Graph'}
                    {!busy && <ArrowRight size={17} />}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Live Bulk Parse Queue Progress */}
          {batchJobs.length > 0 && (
            <Card className="border-brand-200 animate-fade-in">
              <CardHeader className="pb-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <CardTitle className="text-base">Bulk Parse Queue</CardTitle>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {doneCount} of {batchJobs.length} parsed
                      {failedCount > 0 ? ` · ${failedCount} failed` : ''}
                      {hasRunningJobs ? ' · Updating live…' : ' · Batch complete'}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    disabled={completedUploads.length === 0}
                    onClick={() => openReviewQueue()}
                    className="shadow-glow"
                  >
                    Review All ({completedUploads.length})
                    <ArrowRight size={14} />
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-2">
                {batchJobs.map((job) => {
                  const uploadObj = jobToUploadResponse(job)
                  return (
                    <div
                      key={job.id}
                      className="flex flex-col gap-2 rounded-xl border border-slate-200/80 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        {job.status === 'done' ? (
                          <CheckCircle2 size={18} className="shrink-0 text-emerald-600" />
                        ) : job.status === 'failed' ? (
                          <AlertTriangle size={18} className="shrink-0 text-red-500" />
                        ) : job.status === 'processing' ? (
                          <Loader2 size={18} className="shrink-0 animate-spin text-brand-600" />
                        ) : (
                          <Clock size={18} className="shrink-0 text-slate-400" />
                        )}
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <p className="truncate text-sm font-semibold text-slate-900">
                              {job.result_json?.full_name
                                ? `${job.result_json.full_name} — ${job.original_filename}`
                                : job.original_filename}
                            </p>
                            {job.ocr_used && (
                              <Badge variant="brand" className="text-[10px]">
                                <ScanText size={10} />
                                OCR
                              </Badge>
                            )}
                          </div>
                          {job.error_message ? (
                            <p className="text-xs text-red-600">{job.error_message}</p>
                          ) : (
                            <p className="text-xs capitalize text-slate-500">{job.status}</p>
                          )}
                        </div>
                      </div>
                      {uploadObj && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => openReviewQueue(uploadObj)}
                          className="shrink-0"
                        >
                          Review
                        </Button>
                      )}
                    </div>
                  )
                })}
              </CardContent>
            </Card>
          )}
        </div>

        {/* Right 5 Cols: Deliverable Overview */}
        <div className="space-y-5 lg:col-span-5">
          <Card className="overflow-hidden">
            <div className="border-b border-stone-100 mesh-hero p-6 bg-dots">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-white px-3 py-1 text-xs font-semibold text-brand-700 shadow-sm">
                <Network size={13} />
                Included with every upload
              </div>
              <h3 className="mt-3 text-lg font-semibold text-slate-900">
                What happens after upload
              </h3>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Every CV — single or bulk — is parsed into a structured profile with review-before-save
                verification.
              </p>
            </div>
            <CardContent className="space-y-4 pt-5">
              {[
                {
                  icon: Layers,
                  tint: 'bg-brand-50 text-brand-600',
                  title: 'Bulk Queue + Review All Flow',
                  desc: 'Drop up to 25 resumes at once, monitor live per-file progress, and step through every parsed candidate in sequence.',
                },
                {
                  icon: ScanText,
                  tint: 'bg-violet-50 text-violet-600',
                  title: 'Automatic OCR for Scanned PDFs',
                  desc: 'Detects image-only PDFs automatically and falls back to OCR extraction so scanned CVs never fail silently.',
                },
                {
                  icon: ShieldCheck,
                  tint: 'bg-emerald-50 text-emerald-600',
                  title: 'Multi-Signal Duplicate Detection',
                  desc: 'Matches incoming resumes against existing candidates by normalized email, phone, and fuzzy name similarity.',
                },
                {
                  icon: UserCheck,
                  tint: 'bg-sky-50 text-sky-600',
                  title: 'Human-in-the-Loop & Consent Tracking',
                  desc: 'Verify extracted fields, record candidate source and data consent, and inspect the interactive skill network before saving.',
                },
              ].map((item) => {
                const Icon = item.icon
                return (
                  <div key={item.title} className="flex items-start gap-3">
                    <span
                      className={cn(
                        'flex h-9 w-9 shrink-0 items-center justify-center rounded-xl',
                        item.tint,
                      )}
                    >
                      <Icon size={17} />
                    </span>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">{item.title}</p>
                      <p className="mt-0.5 text-xs leading-5 text-slate-500">{item.desc}</p>
                    </div>
                  </div>
                )
              })}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
