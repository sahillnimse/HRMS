import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FileText,
  Loader2,
  Network,
  ShieldCheck,
  Sparkles,
  UserCheck,
  X,
} from 'lucide-react'
import { useResumes } from '@/hooks/useResumes'
import { useCandidates } from '@/hooks/useCandidates'
import { useAddToast } from '@/components/ui/Toast'
import { normalizeProfile, toCandidatePayload, validateProfile } from '@/lib/profile'
import type { ResumeUploadResponse } from '@/types'
import { PageHeader } from '@/components/layout/PageHeader'
import { Stepper } from '@/components/ui/Stepper'
import { ResumeDropzone } from '@/components/ResumeDropzone'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

const PARSE_STAGES = [
  'Extracting text and layout from document',
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

export default function UploadPage() {
  const navigate = useNavigate()
  const addToast = useAddToast()
  const { uploading, uploadError, uploadResume } = useResumes()
  const { createCandidate, loading: autoSaving } = useCandidates()
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [autoSave, setAutoSave] = useState(false)
  const [stageIdx, setStageIdx] = useState(0)

  const busy = uploading || autoSaving

  useEffect(() => {
    if (!uploading) {
      setStageIdx(0)
      return
    }
    const interval = window.setInterval(() => {
      setStageIdx((prev) => (prev < PARSE_STAGES.length - 1 ? prev + 1 : prev))
    }, 1700)
    return () => window.clearInterval(interval)
  }, [uploading])

  const handleUpload = async () => {
    if (!selectedFile) return
    const result = await uploadResume(selectedFile)
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
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="AI Ingestion Pipeline"
        title="Upload & Parse Resume"
        description="Drop a candidate's PDF or DOCX resume. We extract a structured dossier, visualize their skill-to-role network graph, and prepare it for HR verification."
        actions={<Stepper current={uploading ? 1 : 0} />}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left 7 Cols: Dropzone + File Preview + Parsing Progress */}
        <div className="space-y-5 lg:col-span-7">
          <Card>
            <CardHeader className="pb-4">
              <CardTitle>Select Candidate CV</CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <ResumeDropzone
                onFileAccept={(file) => setSelectedFile(file)}
                accepting={uploading}
              />

              {selectedFile && !uploading && (
                <div className="flex items-center gap-3 rounded-xl border border-brand-200 bg-brand-50/40 p-4 animate-fade-in">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white text-brand-600 shadow-sm ring-1 ring-brand-100">
                    <FileText size={20} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold text-slate-900">
                      {selectedFile.name}
                    </p>
                    <p className="text-xs text-slate-500">
                      {(selectedFile.size / 1024 / 1024).toFixed(2)} MB · Ready for AI parsing
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedFile(null)}
                    className="rounded-lg p-1.5 text-slate-400 transition hover:bg-white hover:text-slate-700"
                    aria-label="Remove file"
                  >
                    <X size={16} />
                  </button>
                </div>
              )}

              {uploading && (
                <div className="rounded-2xl border border-brand-200 bg-gradient-to-br from-brand-50/70 to-violet-50/50 p-5 animate-fade-in">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-600 text-white shadow-glow">
                      <Loader2 size={18} className="animate-spin" />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-slate-900">
                        Analyzing {selectedFile?.name}
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
                    <p className="font-semibold">Parsing failed</p>
                    <p className="mt-0.5 text-xs leading-5 text-red-700">{uploadError}</p>
                  </div>
                </div>
              )}

              <div className="flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
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

                <div className="flex items-center justify-end gap-3">
                  <Button variant="outline" onClick={() => navigate('/candidates')} disabled={busy}>
                    Cancel
                  </Button>
                  <Button
                    size="lg"
                    onClick={handleUpload}
                    disabled={!selectedFile || busy}
                    loading={busy}
                    className="shadow-glow"
                  >
                    {autoSaving
                      ? 'Saving Profile…'
                      : uploading
                        ? 'Analyzing Resume…'
                        : 'Parse & Generate Network Graph'}
                    {!busy && <ArrowRight size={17} />}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right 5 Cols: Deliverable Overview */}
        <div className="space-y-5 lg:col-span-5">
          <Card className="overflow-hidden">
            <div className="border-b border-slate-100 bg-gradient-to-br from-brand-50/70 via-white to-violet-50/70 p-6 bg-dots">
              <div className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-white px-3 py-1 text-xs font-semibold text-brand-700 shadow-sm">
                <Network size={13} />
                Included with every upload
              </div>
              <h3 className="mt-3 text-lg font-semibold text-slate-900">
                What happens after upload
              </h3>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Every CV is transformed into an interactive, recruiter-ready profile before anything
                is written to your candidate directory.
              </p>
            </div>
            <CardContent className="space-y-4 pt-5">
              {[
                {
                  icon: Network,
                  tint: 'bg-brand-50 text-brand-600',
                  title: 'Interactive Candidate Network Graph',
                  desc: 'Visualizes roles, technical skills, tools, education, and automatically highlights which skills were used in each job.',
                },
                {
                  icon: Sparkles,
                  tint: 'bg-violet-50 text-violet-600',
                  title: 'Executive Profile Overview',
                  desc: 'Generates a clean summary, seniority tier, completeness score, and structured career timeline.',
                },
                {
                  icon: ShieldCheck,
                  tint: 'bg-emerald-50 text-emerald-600',
                  title: 'Automatic Duplicate Detection',
                  desc: 'Matches incoming resumes against existing PostgreSQL records by email and phone before saving.',
                },
                {
                  icon: UserCheck,
                  tint: 'bg-sky-50 text-sky-600',
                  title: 'Human-in-the-Loop Verification',
                  desc: 'Edit any extracted field side-by-side with the original document before committing to the database.',
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
