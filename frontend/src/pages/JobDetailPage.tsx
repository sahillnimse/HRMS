import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  Building2,
  Check,
  ChevronDown,
  ChevronUp,
  EyeOff,
  FileSpreadsheet,
  FileText,
  GitCompareArrows,
  Kanban,
  MapPin,
  Search,
  Sparkles,
  Trash2,
  UserPlus,
  X,
} from 'lucide-react'
import { useJobs } from '@/hooks/useJobs'
import { useCandidates } from '@/hooks/useCandidates'
import { useAuth } from '@/contexts/AuthContext'
import { blindCandidateLabel, useBlindMode } from '@/contexts/BlindModeContext'
import { downloadBlobFile } from '@/lib/api'
import { useAddToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/layout/PageHeader'
import { KanbanBoard } from '@/components/KanbanBoard'
import { ScoreBreakdownTooltip } from '@/components/ScoreBreakdownTooltip'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Select } from '@/components/ui/Select'
import { Input } from '@/components/ui/Input'
import { Avatar } from '@/components/ui/Avatar'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { cn, formatRelativeDate, formatYears } from '@/lib/utils'
import type { ApplicationStage, JobStatus } from '@/types'

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const { blindMode } = useBlindMode()
  const addToast = useAddToast()
  const {
    jobDetail,
    setJobDetail,
    matches,
    setMatches,
    matchesLoading,
    scoring,
    loading,
    error,
    fetchJobDetail,
    updateJob,
    deleteJob,
    addApplication,
    moveStage,
    removeApplication,
    fetchJobMatches,
    runJobMatch,
  } = useJobs()
  const { candidates, fetchCandidates } = useCandidates()

  const [activeTab, setActiveTab] = useState<'kanban' | 'matches'>('kanban')
  const [compareIds, setCompareIds] = useState<string[]>([])
  const [expandedGapId, setExpandedGapId] = useState<string | null>(null)
  const [showAddModal, setShowAddModal] = useState(false)
  const [candSearch, setCandSearch] = useState('')
  const [addingId, setAddingId] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [exportingXlsx, setExportingXlsx] = useState(false)
  const [exportingPack, setExportingPack] = useState(false)

  const handleExportPackPdf = async () => {
    if (!id || !jobDetail) return
    try {
      setExportingPack(true)
      await downloadBlobFile(
        `/jobs/${id}/shortlist/export/pdf`,
        {
          blind: blindMode,
          candidate_ids: compareIds.length > 0 ? compareIds.join(',') : undefined,
        },
        `${jobDetail.title.toLowerCase().replace(/\s+/g, '-')}-shortlist-pack.pdf`,
      )
      addToast(
        blindMode ? 'Blind Shortlist Pack PDF exported' : 'Shortlist Pack PDF exported',
        'success',
      )
    } catch {
      addToast('Failed to export Shortlist Pack PDF', 'error')
    } finally {
      setExportingPack(false)
    }
  }

  const handleExportXlsx = async () => {
    if (!id || !jobDetail) return
    try {
      setExportingXlsx(true)
      await downloadBlobFile(
        `/jobs/${id}/export/xlsx`,
        { blind: blindMode },
        `${jobDetail.title.toLowerCase().replace(/\s+/g, '-')}-shortlist.xlsx`,
      )
      addToast('Job shortlist XLSX exported', 'success')
    } catch {
      addToast('Failed to export job shortlist', 'error')
    } finally {
      setExportingXlsx(false)
    }
  }

  useEffect(() => {
    if (id) {
      void fetchJobDetail(id)
      void fetchJobMatches(id)
    }
  }, [id, fetchJobDetail, fetchJobMatches])

  useEffect(() => {
    if (showAddModal) {
      void fetchCandidates({ page: 1, page_size: 50, search: candSearch.trim() || undefined })
    }
  }, [showAddModal, candSearch, fetchCandidates])

  const existingCandidateIds = useMemo(
    () => new Set((jobDetail?.applications ?? []).map((a) => a.candidate_id)),
    [jobDetail],
  )

  const toggleCompare = (candidateId: string) => {
    setCompareIds((prev) => {
      if (prev.includes(candidateId)) return prev.filter((item) => item !== candidateId)
      if (prev.length >= 3) return prev
      return [...prev, candidateId]
    })
  }

  const handleStatusChange = async (nextStatus: JobStatus) => {
    if (!id || !jobDetail) return
    const updated = await updateJob(id, { status: nextStatus })
    if (updated) {
      setJobDetail((prev) => (prev ? { ...prev, status: updated.status } : prev))
      addToast(`Job marked as ${nextStatus}`, 'success')
    }
  }

  const handleMoveStage = async (
    applicationId: string,
    toStage: ApplicationStage,
    rejectionReason?: string,
  ) => {
    if (!jobDetail) return
    const previous = jobDetail.applications
    setJobDetail({
      ...jobDetail,
      applications: jobDetail.applications.map((a) =>
        a.id === applicationId
          ? {
              ...a,
              stage: toStage,
              rejection_reason:
                toStage === 'rejected'
                  ? (rejectionReason ?? a.rejection_reason)
                  : a.rejection_reason,
              stage_changed_at: new Date().toISOString(),
            }
          : a,
      ),
    })

    const updated = await moveStage(applicationId, toStage, { rejection_reason: rejectionReason })
    if (!updated) {
      setJobDetail((prev) => (prev ? { ...prev, applications: previous } : prev))
      addToast('Could not move candidate stage', 'error')
      return
    }
    setJobDetail((prev) =>
      prev
        ? {
            ...prev,
            applications: prev.applications.map((a) => (a.id === updated.id ? updated : a)),
          }
        : prev,
    )
    setMatches((prev) =>
      prev.map((m) =>
        m.candidate_id === updated.candidate_id
          ? { ...m, in_pipeline: true, application_stage: updated.stage }
          : m,
      ),
    )
    addToast(`Moved to ${toStage}`, 'success')
  }

  const handleAddCandidate = async (candidateId: string) => {
    if (!id) return
    setAddingId(candidateId)
    const created = await addApplication(candidateId, id, 'applied')
    setAddingId(null)
    if (created) {
      setJobDetail((prev) =>
        prev
          ? {
              ...prev,
              application_count: prev.application_count + 1,
              applications: [created, ...prev.applications],
            }
          : prev,
      )
      setMatches((prev) =>
        prev.map((m) =>
          m.candidate_id === candidateId
            ? { ...m, in_pipeline: true, application_stage: created.stage }
            : m,
        ),
      )
      addToast(`Added ${created.candidate?.full_name || 'candidate'} to pipeline`, 'success')
    } else {
      addToast('Candidate could not be added (may already be in this job)', 'error')
    }
  }

  const handleRemoveApplication = async (applicationId: string) => {
    const removedApp = jobDetail?.applications.find((a) => a.id === applicationId)
    const ok = await removeApplication(applicationId)
    if (ok) {
      setJobDetail((prev) =>
        prev
          ? {
              ...prev,
              application_count: Math.max(0, prev.application_count - 1),
              applications: prev.applications.filter((a) => a.id !== applicationId),
            }
          : prev,
      )
      if (removedApp) {
        setMatches((prev) =>
          prev.map((m) =>
            m.candidate_id === removedApp.candidate_id
              ? { ...m, in_pipeline: false, application_stage: null }
              : m,
          ),
        )
      }
      addToast('Removed candidate from job', 'info')
    }
  }

  const handleRunMatch = async () => {
    if (!id) return
    const result = await runJobMatch(id, { include_explanations: true })
    if (result) {
      setActiveTab('matches')
      addToast(`Scored ${result.length} candidate${result.length === 1 ? '' : 's'}`, 'success')
    } else {
      addToast('Failed to score candidates', 'error')
    }
  }

  const handleDeleteJob = async () => {
    if (!id) return
    setDeleting(true)
    const ok = await deleteJob(id)
    setDeleting(false)
    if (ok) {
      addToast('Job deleted', 'success')
      navigate('/jobs')
    } else {
      addToast('Failed to delete job', 'error')
      setConfirmDelete(false)
    }
  }

  if (loading && !jobDetail) {
    return (
      <div className="space-y-6">
        <div className="skeleton h-12 w-72" />
        <div className="skeleton h-32 w-full rounded-2xl" />
        <div className="skeleton h-96 w-full rounded-2xl" />
      </div>
    )
  }

  if (!jobDetail) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border bg-white p-10 text-center shadow-card">
        <AlertTriangle size={24} className="mx-auto mb-3 text-red-500" />
        <h2 className="text-lg font-semibold text-slate-900">Job not found</h2>
        <p className="mt-1 text-sm text-slate-500">{error || 'This requisition does not exist.'}</p>
        <Button className="mt-5" onClick={() => navigate('/jobs')}>
          Back to Jobs
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        onBack={() => navigate('/jobs')}
        backLabel="All Jobs"
        eyebrow="Job Pipeline"
        title={jobDetail.title}
        description={
          jobDetail.description || 'Drag candidates across stages to track hiring progress.'
        }
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" loading={exportingPack} onClick={() => void handleExportPackPdf()}>
              <FileText size={15} />
              {compareIds.length > 0 ? `Pack PDF (${compareIds.length})` : 'Shortlist Pack PDF'}
            </Button>
            <Button variant="outline" size="sm" loading={exportingXlsx} onClick={() => void handleExportXlsx()}>
              <FileSpreadsheet size={15} />
              Export XLSX
            </Button>
            {canWrite ? (
              <>
                <Select
                  value={jobDetail.status}
                  onChange={(e) => void handleStatusChange(e.target.value as JobStatus)}
                  className="h-9 w-28 text-xs font-semibold capitalize"
                >
                  <option value="open">Open</option>
                  <option value="draft">Draft</option>
                  <option value="closed">Closed</option>
                </Select>
                <Button variant="outline" size="sm" loading={scoring} onClick={() => void handleRunMatch()}>
                  <Sparkles size={15} className="text-brand-600" />
                  {matches.length > 0 ? 'Re-score Matches' : 'Run Match Scoring'}
                </Button>
                <Button size="sm" onClick={() => setShowAddModal(true)} className="shadow-glow">
                  <UserPlus size={15} />
                  Add Candidate
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setConfirmDelete(true)}
                  className="text-red-600 hover:border-red-200 hover:bg-red-50 hover:text-red-700"
                >
                  <Trash2 size={15} />
                  Delete
                </Button>
              </>
            ) : (
              <Badge variant="brand" className="capitalize">
                {jobDetail.status}
              </Badge>
            )}
          </div>
        }
      />

      {/* Job Metadata & Skills Summary */}
      <div className="rounded-2xl border bg-white p-5 shadow-card space-y-3">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-slate-600">
          {jobDetail.department && (
            <span className="inline-flex items-center gap-1.5 font-medium">
              <Building2 size={14} className="text-slate-400" />
              {jobDetail.department}
            </span>
          )}
          {jobDetail.location && (
            <span className="inline-flex items-center gap-1.5 font-medium">
              <MapPin size={14} className="text-slate-400" />
              {jobDetail.location}
            </span>
          )}
          {(jobDetail.min_years != null || jobDetail.max_years != null) && (
            <Badge variant="secondary">
              Experience: {jobDetail.min_years ?? 0}–{jobDetail.max_years ?? '15+'} yrs
            </Badge>
          )}
          <Badge variant="brand">
            {jobDetail.applications.length} candidate
            {jobDetail.applications.length === 1 ? '' : 's'} in pipeline
          </Badge>
        </div>

        {(jobDetail.required_skills.length > 0 || jobDetail.nice_to_have_skills.length > 0) && (
          <div className="flex flex-wrap items-center gap-1.5 border-t border-slate-100 pt-3">
            {jobDetail.required_skills.map((sk) => (
              <span
                key={`req-${sk}`}
                className="rounded-md border border-violet-200 bg-violet-50 px-2 py-0.5 text-xs font-medium text-violet-800"
              >
                {sk}
              </span>
            ))}
            {jobDetail.nice_to_have_skills.map((sk) => (
              <span
                key={`nice-${sk}`}
                className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-800"
              >
                {sk} (nice to have)
              </span>
            ))}
          </div>
        )}
      </div>

      {/* View Tabs: Kanban Board | Ranked Matches */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
          <button
            type="button"
            onClick={() => setActiveTab('kanban')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-semibold transition',
              activeTab === 'kanban'
                ? 'bg-brand-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900',
            )}
          >
            <Kanban size={14} />
            Kanban Board
            <span
              className={cn(
                'rounded-full px-1.5 py-0.5 text-[10px]',
                activeTab === 'kanban'
                  ? 'bg-white/20 text-white'
                  : 'bg-slate-100 text-slate-600',
              )}
            >
              {jobDetail.applications.length}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('matches')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-xs font-semibold transition',
              activeTab === 'matches'
                ? 'bg-brand-600 text-white shadow-sm'
                : 'text-slate-600 hover:text-slate-900',
            )}
          >
            <Sparkles size={14} />
            Ranked Matches
            <span
              className={cn(
                'rounded-full px-1.5 py-0.5 text-[10px]',
                activeTab === 'matches'
                  ? 'bg-white/20 text-white'
                  : 'bg-slate-100 text-slate-600',
              )}
            >
              {matches.length}
            </span>
          </button>
        </div>

        {activeTab === 'matches' && compareIds.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-600">
              {compareIds.length}/3 selected
            </span>
            <Button variant="ghost" size="sm" onClick={() => setCompareIds([])}>
              Clear
            </Button>
            <Button
              size="sm"
              disabled={compareIds.length < 2}
              onClick={() => navigate(`/compare?ids=${compareIds.join(',')}&jobId=${jobDetail.id}`)}
            >
              <GitCompareArrows size={14} />
              Compare ({compareIds.length})
            </Button>
          </div>
        )}
      </div>

      {/* Tab 1: Drag-and-Drop Kanban Board */}
      {activeTab === 'kanban' && (
        <KanbanBoard
          applications={jobDetail.applications}
          canWrite={canWrite}
          onMoveStage={handleMoveStage}
          onRemoveApplication={handleRemoveApplication}
        />
      )}

      {/* Tab 2: Deterministic Ranked Matches */}
      {activeTab === 'matches' && (
        <div className="space-y-4">
          {matchesLoading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => (
                <div key={i} className="skeleton h-24 w-full rounded-2xl" />
              ))}
            </div>
          ) : matches.length === 0 ? (
            <div className="rounded-2xl border bg-white p-12 text-center shadow-card">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                <Sparkles size={22} />
              </div>
              <h3 className="text-base font-semibold text-slate-900">No match scores yet</h3>
              <p className="mx-auto mt-1 max-w-md text-sm text-slate-500">
                Score every saved candidate against this job using deterministic skill coverage
                (45%), experience fit (25%), nice-to-have skills (15%), and semantic similarity
                (15%).
              </p>
              {canWrite && (
                <Button className="mt-5 shadow-glow" loading={scoring} onClick={() => void handleRunMatch()}>
                  <Sparkles size={15} />
                  Run Match Scoring
                </Button>
              )}
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-500">
                <span>
                  Select 2–3 candidates to compare side-by-side. Hover or click any score pill to
                  inspect the full breakdown.
                </span>
                <span>Updated {formatRelativeDate(matches[0].computed_at)}</span>
              </div>

              {matches.map((m, idx) => {
                const cand = m.candidate
                const isSelected = compareIds.includes(m.candidate_id)
                const selectDisabled = !isSelected && compareIds.length >= 3
                return (
                  <div
                    key={m.id}
                    className={cn(
                      'rounded-2xl border bg-white p-4 shadow-card transition',
                      isSelected
                        ? 'border-brand-400 ring-2 ring-brand-500/15'
                        : 'border-slate-200/80 hover:border-slate-300',
                    )}
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="flex min-w-0 flex-1 items-start gap-3">
                        <button
                          type="button"
                          disabled={selectDisabled}
                          onClick={() => toggleCompare(m.candidate_id)}
                          title={
                            isSelected
                              ? 'Remove from comparison'
                              : selectDisabled
                                ? 'Select up to 3 candidates'
                                : 'Select to compare'
                          }
                          className={cn(
                            'mt-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border transition',
                            isSelected
                              ? 'border-brand-600 bg-brand-600 text-white'
                              : selectDisabled
                                ? 'cursor-not-allowed border-slate-200 bg-slate-50 text-slate-300'
                                : 'border-slate-300 bg-white text-transparent hover:border-brand-400',
                          )}
                          aria-label={isSelected ? 'Deselect candidate' : 'Select candidate to compare'}
                        >
                          <Check size={13} />
                        </button>

                        <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-xs font-bold text-slate-700 tabular-nums">
                          #{idx + 1}
                        </span>

                        {cand &&
                          (blindMode ? (
                            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
                              <EyeOff size={18} />
                            </div>
                          ) : (
                            <Avatar name={cand.full_name} size="md" />
                          ))}

                        <div className="min-w-0 flex-1 space-y-1.5">
                          <div className="flex flex-wrap items-center gap-2">
                            <Link
                              to={`/candidates/${m.candidate_id}`}
                              className="truncate text-sm font-semibold text-slate-900 hover:text-brand-600"
                            >
                              {blindMode
                                ? blindCandidateLabel(m.candidate_id)
                                : cand?.full_name ?? 'Candidate'}
                            </Link>
                            {cand?.primary_domain && (
                              <Badge variant="brand">{cand.primary_domain}</Badge>
                            )}
                            {cand && (
                              <span className="text-xs text-slate-500">
                                {formatYears(cand.years_experience)}
                                {cand.city ? ` · ${cand.city}` : ''}
                              </span>
                            )}
                          </div>

                          {(m.breakdown?.why || m.explanation) && (
                            <p className="text-xs leading-5 text-slate-600">
                              {m.breakdown?.why || m.explanation}
                            </p>
                          )}

                          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                            {(m.breakdown?.matched_required_skills ?? []).slice(0, 5).map((sk) => (
                              <span
                                key={`mreq-${m.id}-${sk}`}
                                className="rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700"
                              >
                                {sk}
                              </span>
                            ))}
                            {(m.breakdown?.missing_required_skills ?? []).slice(0, 3).map((sk) => (
                              <span
                                key={`mmis-${m.id}-${sk}`}
                                className="rounded bg-rose-50 px-1.5 py-0.5 text-[11px] font-medium text-rose-700 line-through decoration-rose-400"
                              >
                                {sk}
                              </span>
                            ))}
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedGapId((prev) => (prev === m.id ? null : m.id))
                              }
                              aria-expanded={expandedGapId === m.id}
                              className="inline-flex items-center gap-1 rounded-md border border-stone-200 bg-stone-50 px-2 py-0.5 text-[11px] font-semibold text-slate-600 transition hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
                            >
                              Skill-gap view
                              {expandedGapId === m.id ? (
                                <ChevronUp size={12} />
                              ) : (
                                <ChevronDown size={12} />
                              )}
                            </button>
                          </div>

                          {expandedGapId === m.id && (
                            <div className="mt-3 rounded-xl border border-stone-200/80 bg-stone-50/70 p-3.5 text-xs space-y-2.5 animate-fade-in">
                              <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                                <div>
                                  <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-emerald-700">
                                    Matched Required ({m.breakdown?.matched_required_skills?.length ?? 0})
                                  </p>
                                  <div className="flex flex-wrap gap-1">
                                    {(m.breakdown?.matched_required_skills ?? []).length > 0 ? (
                                      m.breakdown.matched_required_skills.map((sk) => (
                                        <span
                                          key={`gmr-${m.id}-${sk}`}
                                          className="rounded bg-emerald-100/80 px-1.5 py-0.5 text-[11px] font-medium text-emerald-800"
                                        >
                                          {sk}
                                        </span>
                                      ))
                                    ) : (
                                      <span className="text-slate-400">None</span>
                                    )}
                                  </div>
                                </div>

                                <div>
                                  <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-rose-700">
                                    Missing Required ({m.breakdown?.missing_required_skills?.length ?? 0})
                                  </p>
                                  <div className="flex flex-wrap gap-1">
                                    {(m.breakdown?.missing_required_skills ?? []).length > 0 ? (
                                      m.breakdown.missing_required_skills.map((sk) => (
                                        <span
                                          key={`gmis-${m.id}-${sk}`}
                                          className="rounded bg-rose-100/80 px-1.5 py-0.5 text-[11px] font-medium text-rose-800"
                                        >
                                          {sk}
                                        </span>
                                      ))
                                    ) : (
                                      <span className="text-emerald-700 font-medium">All covered</span>
                                    )}
                                  </div>
                                </div>

                                <div>
                                  <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-sky-700">
                                    Adjacent / Transferable ({m.breakdown?.adjacent_skills?.length ?? 0})
                                  </p>
                                  <div className="flex flex-wrap gap-1">
                                    {(m.breakdown?.adjacent_skills ?? []).length > 0 ? (
                                      (m.breakdown.adjacent_skills ?? []).map((adj, aIdx) => (
                                        <span
                                          key={`gadj-${m.id}-${aIdx}`}
                                          title={adj.relation}
                                          className="rounded bg-sky-100/80 px-1.5 py-0.5 text-[11px] font-medium text-sky-800"
                                        >
                                          {adj.candidate_skill} → {adj.required_skill}
                                        </span>
                                      ))
                                    ) : (
                                      <span className="text-slate-400">None detected</span>
                                    )}
                                  </div>
                                </div>
                              </div>

                              <div className="flex flex-wrap items-center justify-between gap-2 border-t border-stone-200/70 pt-2 text-[11px] text-slate-600">
                                <span>
                                  Experience fit:{' '}
                                  <span className="font-semibold text-slate-800">
                                    {m.breakdown?.candidate_years ?? 0} yrs
                                  </span>{' '}
                                  {m.breakdown?.job_min_years != null ||
                                  m.breakdown?.job_max_years != null
                                    ? `(target ${m.breakdown?.job_min_years ?? 0}–${m.breakdown?.job_max_years ?? '15+'} yrs · ${Math.round(m.breakdown?.experience_score ?? 0)}%)`
                                    : `(${Math.round(m.breakdown?.experience_score ?? 0)}%)`}
                                </span>
                                <span>
                                  Semantic fit:{' '}
                                  <span className="font-semibold text-slate-800">
                                    {Math.round(m.breakdown?.semantic_score ?? 0)}%
                                  </span>{' '}
                                  ({m.breakdown?.semantic_mode === 'embedding' ? 'vector' : 'lexical'})
                                </span>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="flex shrink-0 flex-wrap items-center gap-2.5 lg:flex-col lg:items-end">
                        <ScoreBreakdownTooltip
                          score={m.score}
                          breakdown={m.breakdown}
                          align="right"
                        />

                        {m.in_pipeline ? (
                          <Badge variant="secondary" className="capitalize">
                            In pipeline · {m.application_stage || 'applied'}
                          </Badge>
                        ) : canWrite ? (
                          <Button
                            size="sm"
                            variant="outline"
                            loading={addingId === m.candidate_id}
                            onClick={() => void handleAddCandidate(m.candidate_id)}
                          >
                            <UserPlus size={13} />
                            Add to Pipeline
                          </Button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Add Candidate Modal */}
      {showAddModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm"
            onClick={() => setShowAddModal(false)}
          />
          <div className="relative flex max-h-[85vh] w-full max-w-lg flex-col rounded-2xl border bg-white p-6 shadow-2xl animate-fade-in">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-semibold text-slate-900">
                Add Candidate to {jobDetail.title}
              </h3>
              <button
                type="button"
                onClick={() => setShowAddModal(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>

            <div className="relative mt-4">
              <Search
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <Input
                value={candSearch}
                onChange={(e) => setCandSearch(e.target.value)}
                placeholder="Search saved candidates…"
                className="pl-9"
              />
            </div>

            <div className="mt-4 flex-1 space-y-2 overflow-y-auto pr-1">
              {candidates.length === 0 ? (
                <p className="py-8 text-center text-sm text-slate-500">No candidates found.</p>
              ) : (
                candidates.map((c) => {
                  const alreadyIn = existingCandidateIds.has(c.id)
                  return (
                    <div
                      key={c.id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-slate-200/80 p-3"
                    >
                      <div className="flex min-w-0 items-center gap-2.5">
                        <Avatar name={c.full_name} size="sm" />
                        <div className="min-w-0">
                          <p className="truncate text-sm font-semibold text-slate-900">
                            {c.full_name}
                          </p>
                          <p className="truncate text-xs text-slate-500">
                            {c.primary_domain} · {c.years_experience} yrs
                          </p>
                        </div>
                      </div>
                      {alreadyIn ? (
                        <Badge variant="secondary">In pipeline</Badge>
                      ) : (
                        <Button
                          size="sm"
                          loading={addingId === c.id}
                          onClick={() => void handleAddCandidate(c.id)}
                        >
                          Add
                        </Button>
                      )}
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete "${jobDetail.title}"?`}
        description="This permanently deletes the job requisition and its pipeline applications."
        confirmLabel="Delete Job"
        loading={deleting}
        onConfirm={handleDeleteJob}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  )
}
