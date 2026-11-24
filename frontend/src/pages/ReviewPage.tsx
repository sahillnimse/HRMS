import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Edit3,
  LayoutDashboard,
  Network,
  Save,
  Upload,
} from 'lucide-react'
import { useCandidates } from '@/hooks/useCandidates'
import { useAddToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/layout/PageHeader'
import { Stepper } from '@/components/ui/Stepper'
import { Tabs } from '@/components/ui/Tabs'
import { Button } from '@/components/ui/Button'
import { CandidateNetworkGraph } from '@/components/CandidateNetworkGraph'
import { CandidateProfileOverview } from '@/components/CandidateProfileOverview'
import { EditableReview } from '@/components/EditableReview'
import { normalizeProfile, toCandidatePayload, validateProfile } from '@/lib/profile'
import type { CandidateResponse, CandidateUpdate, ParsedResumeData, ResumeUploadResponse } from '@/types'

type ReviewTab = 'dossier' | 'edit'

export default function ReviewPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const addToast = useAddToast()
  const { createCandidate, loading: saving, error: saveError } = useCandidates()

  const upload = (location.state as { upload?: ResumeUploadResponse } | null)?.upload

  const [draft, setDraft] = useState<ParsedResumeData | null>(() =>
    upload ? normalizeProfile(upload.parsed_data) : null,
  )
  const [tab, setTab] = useState<ReviewTab>('dossier')
  const [savedCandidate, setSavedCandidate] = useState<CandidateResponse | null>(null)

  useEffect(() => {
    if (!upload) {
      navigate('/upload', { replace: true })
    }
  }, [upload, navigate])

  if (!upload || !draft) return null

  const commitSave = async (payload: CandidateUpdate) => {
    const result = await createCandidate({
      resume_file_id: upload.resume_file_id,
      ...payload,
    })
    if (result) {
      setSavedCandidate(result)
      addToast(`${result.full_name} saved to candidate directory`, 'success')
    } else {
      addToast('Failed to save candidate. Check duplicate or required fields.', 'error')
    }
  }

  const handleQuickSave = async () => {
    const errs = validateProfile(draft)
    if (Object.keys(errs).length > 0) {
      setTab('edit')
      addToast('Please fill in the required fields before saving.', 'error')
      return
    }
    await commitSave(toCandidatePayload(draft))
  }

  if (savedCandidate) {
    return (
      <div className="mx-auto max-w-2xl py-10 animate-fade-in">
        <div className="rounded-2xl border bg-white p-10 text-center shadow-card">
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600 ring-8 ring-emerald-50/50">
            <CheckCircle2 size={32} />
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-slate-900">
            Candidate Saved Successfully
          </h2>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
            <span className="font-semibold text-slate-800">{savedCandidate.full_name}</span> has
            been added to your talent directory with their structured profile and network graph.
          </p>
          <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
            <Button size="lg" onClick={() => navigate(`/candidates/${savedCandidate.id}`)}>
              View Full Profile
              <ArrowUpRight size={16} />
            </Button>
            <Button variant="outline" size="lg" onClick={() => navigate('/')}>
              Go to Dashboard
            </Button>
            <Button variant="soft" size="lg" onClick={() => navigate('/upload')}>
              <Upload size={16} />
              Upload Another
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
        eyebrow="Step 3 · Human-in-the-Loop Verification"
        title={draft.full_name || 'Review Parsed Candidate'}
        description="Inspect the auto-generated network graph and full dossier below. Edit any detail before saving to PostgreSQL."
        actions={
          <div className="flex flex-wrap items-center gap-3">
            <Stepper current={2} />
            <Button onClick={handleQuickSave} loading={saving} className="shadow-glow">
              <Save size={16} />
              Save Candidate
            </Button>
          </div>
        }
      />

      {/* Duplicate Alert */}
      {upload.duplicate.is_duplicate && (
        <div className="flex flex-col gap-3 rounded-2xl border border-amber-200 bg-amber-50/80 p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <AlertTriangle size={20} className="mt-0.5 shrink-0 text-amber-600" />
            <div>
              <p className="text-sm font-semibold text-amber-900">
                Potential duplicate candidate detected (matched by {upload.duplicate.matched_field})
              </p>
              <p className="mt-0.5 text-xs text-amber-800">
                A candidate with the same {upload.duplicate.matched_field} already exists in the
                database. Inspect the existing profile or update the contact fields before saving.
              </p>
            </div>
          </div>
          {upload.duplicate.candidate_id && (
            <Button variant="outline" size="sm" asChild className="shrink-0 bg-white">
              <Link
                to={`/candidates/${upload.duplicate.candidate_id}`}
                target="_blank"
                rel="noopener noreferrer"
              >
                View Existing
                <ArrowUpRight size={14} />
              </Link>
            </Button>
          )}
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
          onSave={commitSave}
          onCancel={() => setTab('dossier')}
          saving={saving}
          submitLabel="Save Candidate"
          cancelLabel="Back to Overview"
        />
      )}
    </div>
  )
}
