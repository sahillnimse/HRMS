import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  ArrowUpRight,
  CheckCircle2,
  Edit3,
  LayoutDashboard,
  Network,
  RefreshCw,
  Save,
  ScanText,
  SkipForward,
  Upload,
  UserPlus,
} from 'lucide-react'
import { useCandidates } from '@/hooks/useCandidates'
import { useAddToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/layout/PageHeader'
import { Stepper } from '@/components/ui/Stepper'
import { Tabs } from '@/components/ui/Tabs'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { CandidateNetworkGraph } from '@/components/CandidateNetworkGraph'
import { CandidateProfileOverview } from '@/components/CandidateProfileOverview'
import { EditableReview } from '@/components/EditableReview'
import { normalizeProfile, toCandidatePayload, validateProfile } from '@/lib/profile'
import type {
  CandidateResponse,
  CandidateUpdate,
  ParsedResumeData,
  ResumeUploadResponse,
} from '@/types'

type ReviewTab = 'dossier' | 'edit'

const PENDING_CACHE_KEY = 'hrms_pending_uploads'

function loadFallbackUpload(): ResumeUploadResponse | undefined {
  try {
    const lastId = window.sessionStorage.getItem('hrms_last_upload_id')
    const raw = window.sessionStorage.getItem(PENDING_CACHE_KEY)
    if (!raw || !lastId) return undefined
    const map = JSON.parse(raw) as Record<string, ResumeUploadResponse>
    return map[lastId]
  } catch {
    return undefined
  }
}

function clearCachedUpload(resumeFileId: string) {
  try {
    const raw = window.sessionStorage.getItem(PENDING_CACHE_KEY)
    if (!raw) return
    const map = JSON.parse(raw) as Record<string, ResumeUploadResponse>
    delete map[resumeFileId]
    window.sessionStorage.setItem(PENDING_CACHE_KEY, JSON.stringify(map))
  } catch {
    // Ignore storage errors
  }
}

export default function ReviewPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const addToast = useAddToast()
  const { createCandidate, updateCandidate, loading: saving, error: saveError } = useCandidates()

  const state = location.state as {
    upload?: ResumeUploadResponse
    queue?: ResumeUploadResponse[]
  } | null

  const initialQueue: ResumeUploadResponse[] =
    state?.queue && state.queue.length > 0
      ? state.queue
      : state?.upload
        ? [state.upload]
        : (() => {
            const fb = loadFallbackUpload()
            return fb ? [fb] : []
          })()

  const [queue] = useState<ResumeUploadResponse[]>(initialQueue)
  const [queueIdx, setQueueIdx] = useState(0)
  const [savedCount, setSavedCount] = useState(0)
  const upload = queue[queueIdx]

  const [draft, setDraft] = useState<ParsedResumeData | null>(() =>
    upload ? normalizeProfile(upload.parsed_data) : null,
  )
  const [tab, setTab] = useState<ReviewTab>('dossier')
  const [savedCandidate, setSavedCandidate] = useState<CandidateResponse | null>(null)
  const [savedMode, setSavedMode] = useState<'created' | 'updated'>('created')

  useEffect(() => {
    if (queue.length === 0) {
      navigate('/upload', { replace: true })
    }
  }, [queue.length, navigate])

  useEffect(() => {
    if (upload) {
      setDraft(normalizeProfile(upload.parsed_data))
      setTab('dossier')
    }
  }, [upload])

  if (!upload || !draft) return null

  const isMultiQueue = queue.length > 1
  const hasMoreInQueue = queueIdx < queue.length - 1
  const duplicateMatches = upload.duplicate.matches ?? []
  const hasDuplicates = upload.duplicate.is_duplicate && duplicateMatches.length > 0

  const advanceOrFinish = (result: CandidateResponse, mode: 'created' | 'updated') => {
    setSavedCount((c) => c + 1)
    if (hasMoreInQueue) {
      setQueueIdx((i) => i + 1)
    } else {
      setSavedMode(mode)
      setSavedCandidate(result)
    }
  }

  const commitCreate = async (payload: CandidateUpdate, allowDuplicate: boolean) => {
    const result = await createCandidate({
      resume_file_id: upload.resume_file_id,
      ...payload,
      allow_duplicate: allowDuplicate,
      is_duplicate_flagged: hasDuplicates,
    })
    if (result) {
      clearCachedUpload(upload.resume_file_id)
      addToast(`${result.full_name} saved to candidate directory`, 'success')
      advanceOrFinish(result, 'created')
    } else {
      addToast('Failed to save candidate. Check duplicate or required fields.', 'error')
    }
  }

  const handleSaveAsNew = async () => {
    const errs = validateProfile(draft)
    if (Object.keys(errs).length > 0) {
      setTab('edit')
      addToast('Please fill in the required fields before saving.', 'error')
      return
    }
    await commitCreate(toCandidatePayload(draft), hasDuplicates)
  }

  const handleUpdateExisting = async (existingId: string) => {
    const errs = validateProfile(draft)
    if (Object.keys(errs).length > 0) {
      setTab('edit')
      addToast('Please fill in the required fields before updating.', 'error')
      return
    }
    const payload = {
      ...toCandidatePayload(draft),
      resume_file_id: upload.resume_file_id,
      is_duplicate_flagged: false,
    }
    const result = await updateCandidate(existingId, payload)
    if (result) {
      clearCachedUpload(upload.resume_file_id)
      addToast(`Updated existing profile for ${result.full_name}`, 'success')
      advanceOrFinish(result, 'updated')
    } else {
      addToast('Failed to update existing candidate.', 'error')
    }
  }

  const handleSkipCurrent = () => {
    if (hasMoreInQueue) {
      setQueueIdx((i) => i + 1)
    } else {
      navigate('/candidates')
    }
  }

  if (savedCandidate) {
    return (
      <div className="mx-auto max-w-2xl py-10 animate-fade-in">
        <div className="rounded-2xl border bg-white p-10 text-center shadow-card">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600 ring-8 ring-emerald-50/50">
            <CheckCircle2 size={32} />
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">
            {isMultiQueue
              ? `Batch Review Complete (${savedCount} Saved)`
              : savedMode === 'updated'
                ? 'Existing Candidate Updated'
                : 'Candidate Saved Successfully'}
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
            <span className="font-semibold text-slate-800">{savedCandidate.full_name}</span>{' '}
            {savedMode === 'updated'
              ? 'has been updated with the latest resume and parsed profile.'
              : 'has been added to your talent directory with their structured profile and network graph.'}
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <Button size="lg" onClick={() => navigate(`/candidates/${savedCandidate.id}`)}>
              View Full Profile
              <ArrowUpRight size={16} />
            </Button>
            <Button variant="outline" size="lg" onClick={() => navigate('/candidates')}>
              Go to Candidates
            </Button>
            <Button variant="soft" size="lg" onClick={() => navigate('/upload')}>
              <Upload size={16} />
              Upload More
            </Button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        onBack={() => navigate('/upload')}
        backLabel="Back to Upload"
        eyebrow={
          isMultiQueue
            ? `Bulk Review Queue · Candidate ${queueIdx + 1} of ${queue.length}`
            : 'Step 3 · Human-in-the-Loop Verification'
        }
        title={draft.full_name || 'Review Parsed Candidate'}
        description="Inspect the auto-generated network graph and full dossier below. Edit any detail before saving to PostgreSQL."
        actions={
          <div className="flex flex-wrap items-center gap-2.5">
            {upload.ocr_used && (
              <Badge variant="brand">
                <ScanText size={12} />
                Extracted via OCR
              </Badge>
            )}
            {!isMultiQueue && <Stepper current={2} />}
            {isMultiQueue && (
              <Button variant="outline" size="sm" onClick={handleSkipCurrent} disabled={saving}>
                <SkipForward size={14} />
                {hasMoreInQueue ? 'Skip' : 'Finish'}
              </Button>
            )}
            <Button onClick={handleSaveAsNew} loading={saving} className="shadow-glow">
              {hasDuplicates ? <UserPlus size={16} /> : <Save size={16} />}
              {hasMoreInQueue
                ? hasDuplicates
                  ? 'Save New & Next'
                  : 'Save & Next'
                : hasDuplicates
                  ? 'Save as New'
                  : 'Save Candidate'}
              {hasMoreInQueue && <ArrowRight size={15} />}
            </Button>
          </div>
        }
      />

      {isMultiQueue && (
        <div className="rounded-2xl border border-brand-200 bg-brand-50/50 px-5 py-3">
          <div className="flex items-center justify-between text-xs font-medium text-brand-900">
            <span>
              Reviewing <span className="font-bold">{queueIdx + 1}</span> of{' '}
              <span className="font-bold">{queue.length}</span> parsed resumes
            </span>
            <span>{savedCount} saved so far</span>
          </div>
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-brand-100">
            <div
              className="h-full rounded-full bg-brand-600 transition-all"
              style={{ width: `${Math.round(((queueIdx + 1) / queue.length) * 100)}%` }}
            />
          </div>
        </div>
      )}

      {/* Multi-Match Duplicate Resolution Panel */}
      {hasDuplicates && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-5 space-y-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-start gap-3">
              <AlertTriangle size={20} className="mt-0.5 shrink-0 text-amber-600" />
              <div>
                <p className="text-sm font-semibold text-amber-950">
                  {duplicateMatches.length} potential duplicate
                  {duplicateMatches.length === 1 ? '' : 's'} detected
                </p>
                <p className="mt-0.5 text-xs text-amber-800">
                  Choose <span className="font-semibold">Update Existing</span> to refresh a matched
                  record with this CV, or <span className="font-semibold">Save as New</span> to
                  create a separate flagged profile.
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={handleSaveAsNew}
              loading={saving}
              className="shrink-0 bg-white"
            >
              <UserPlus size={14} />
              Save as New (Flagged)
            </Button>
          </div>

          <div className="space-y-2">
            {duplicateMatches.map((match) => (
              <div
                key={match.candidate_id}
                className="flex flex-col gap-3 rounded-xl border border-amber-200/80 bg-white p-3.5 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold text-slate-900">{match.full_name}</span>
                    <Badge variant="secondary">{match.primary_domain}</Badge>
                    {match.matched_fields.map((field) => (
                      <Badge key={field} variant="warning">
                        Matched: {field}
                        {field === 'name' && match.name_similarity != null
                          ? ` (${Math.round(match.name_similarity * 100)}%)`
                          : ''}
                      </Badge>
                    ))}
                  </div>
                  <p className="truncate text-xs text-slate-500">
                    {[match.email, match.phone].filter(Boolean).join(' · ') || 'No contact info'}
                  </p>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  <Button variant="outline" size="sm" asChild>
                    <Link
                      to={`/candidates/${match.candidate_id}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Inspect
                      <ArrowUpRight size={13} />
                    </Link>
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => handleUpdateExisting(match.candidate_id)}
                    loading={saving}
                  >
                    <RefreshCw size={13} />
                    Update Existing
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {saveError && (
        <div className="flex items-center gap-2 rounded-2xl border border-red-200 bg-red-50 px-5 py-3.5 text-sm text-red-800">
          <AlertTriangle size={17} className="shrink-0 text-red-600" />
          {saveError}
        </div>
      )}

      {/* Prominent Interactive Network Graph immediately visible on CV upload */}
      <CandidateNetworkGraph
        profile={draft}
        title={`${draft.full_name || 'Candidate'} — Extracted Talent Network`}
        subtitle="Live interactive graph generated from the uploaded resume · drag nodes or click to inspect connections"
        height={500}
      />

      {/* Tabs: Detailed Profile Overview vs Edit Form */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Tabs
          value={tab}
          onChange={setTab}
          items={[
            { value: 'dossier', label: 'Detailed Profile Overview', icon: LayoutDashboard },
            { value: 'edit', label: 'Edit Parsed Fields', icon: Edit3 },
          ]}
        />
        <span className="inline-flex items-center gap-1.5 text-xs text-slate-500">
          <Network size={14} className="text-brand-600" />
          Graph updates live as you edit
        </span>
      </div>

      {tab === 'dossier' ? (
        <CandidateProfileOverview
          profile={draft}
          rawParsedData={draft.raw_parsed_data}
          resumeFileId={upload.resume_file_id}
          showGraph={false}
          headerActions={
            <Button variant="soft" size="sm" onClick={() => setTab('edit')}>
              <Edit3 size={14} />
              Edit Fields
            </Button>
          }
        />
      ) : (
        <EditableReview
          parsedData={draft}
          duplicate={upload.duplicate}
          resumeFileId={upload.resume_file_id}
          onChange={setDraft}
          onSave={(payload) => commitCreate(payload, hasDuplicates)}
          onCancel={() => setTab('dossier')}
          saving={saving}
          submitLabel={hasDuplicates ? 'Save as New' : 'Save Candidate'}
          cancelLabel="Back to Overview"
        />
      )}
    </div>
  )
}
