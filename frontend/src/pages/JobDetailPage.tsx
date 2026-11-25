import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  Building2,
  MapPin,
  Search,
  Trash2,
  UserPlus,
  X,
} from 'lucide-react'
import { useJobs } from '@/hooks/useJobs'
import { useCandidates } from '@/hooks/useCandidates'
import { useAuth } from '@/contexts/AuthContext'
import { useAddToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/layout/PageHeader'
import { KanbanBoard } from '@/components/KanbanBoard'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Select } from '@/components/ui/Select'
import { Input } from '@/components/ui/Input'
import { Avatar } from '@/components/ui/Avatar'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import type { ApplicationStage, JobStatus } from '@/types'

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const addToast = useAddToast()
  const {
    jobDetail,
    setJobDetail,
    loading,
    error,
    fetchJobDetail,
    updateJob,
    deleteJob,
    addApplication,
    moveStage,
    removeApplication,
  } = useJobs()
  const { candidates, fetchCandidates } = useCandidates()

  const [showAddModal, setShowAddModal] = useState(false)
  const [candSearch, setCandSearch] = useState('')
  const [addingId, setAddingId] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (id) void fetchJobDetail(id)
  }, [id, fetchJobDetail])

  useEffect(() => {
    if (showAddModal) {
      void fetchCandidates({ page: 1, page_size: 50, search: candSearch.trim() || undefined })
    }
  }, [showAddModal, candSearch, fetchCandidates])

  const existingCandidateIds = useMemo(
    () => new Set((jobDetail?.applications ?? []).map((a) => a.candidate_id)),
    [jobDetail],
  )

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
              rejection_reason: toStage === 'rejected' ? rejectionReason ?? a.rejection_reason : a.rejection_reason,
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
      addToast(`Added ${created.candidate?.full_name || 'candidate'} to pipeline`, 'success')
    } else {
      addToast('Candidate could not be added (may already be in this job)', 'error')
    }
  }

  const handleRemoveApplication = async (applicationId: string) => {
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
      addToast('Removed candidate from job', 'info')
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
          canWrite ? (
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
          )
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

      {/* Drag-and-Drop Kanban Board */}
      <KanbanBoard
        applications={jobDetail.applications}
        canWrite={canWrite}
        onMoveStage={handleMoveStage}
        onRemoveApplication={handleRemoveApplication}
      />

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
