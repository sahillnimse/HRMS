import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowUpRight,
  Briefcase,
  Building2,
  MapPin,
  Plus,
  Search,
  Trash2,
  Users,
  X,
} from 'lucide-react'
import { useJobs } from '@/hooks/useJobs'
import { useAuth } from '@/contexts/AuthContext'
import { useAddToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/layout/PageHeader'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { Badge } from '@/components/ui/Badge'
import { TagInput } from '@/components/ui/TagInput'
import { cn, formatRelativeDate } from '@/lib/utils'
import type { JobItem, JobPayload, JobStatus } from '@/types'

const STATUS_BADGE: Record<JobStatus, 'success' | 'warning' | 'secondary'> = {
  open: 'success',
  draft: 'warning',
  closed: 'secondary',
}

const EMPTY_JOB: JobPayload = {
  title: '',
  department: '',
  location: '',
  description: '',
  required_skills: [],
  nice_to_have_skills: [],
  min_years: null,
  max_years: null,
  status: 'open',
}

export default function JobsPage() {
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const addToast = useAddToast()
  const { jobs, loading, error, fetchJobs, createJob, deleteJob } = useJobs()

  const [statusFilter, setStatusFilter] = useState<JobStatus | 'all'>('all')
  const [search, setSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState<JobPayload>(EMPTY_JOB)
  const [creating, setCreating] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<JobItem | null>(null)
  const [deleting, setDeleting] = useState(false)

  const handleConfirmDeleteJob = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    const ok = await deleteJob(deleteTarget.id)
    setDeleting(false)
    if (ok) {
      addToast(`Deleted job "${deleteTarget.title}"`, 'success')
      setDeleteTarget(null)
      void fetchJobs({
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search.trim() || undefined,
      })
    } else {
      addToast('Failed to delete job', 'error')
    }
  }

  useEffect(() => {
    const t = window.setTimeout(() => {
      void fetchJobs({
        status: statusFilter === 'all' ? undefined : statusFilter,
        search: search.trim() || undefined,
      })
    }, 200)
    return () => window.clearTimeout(t)
  }, [fetchJobs, statusFilter, search])

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.title.trim()) return
    setCreating(true)
    const created = await createJob(form)
    setCreating(false)
    if (created) {
      addToast(`Created job "${created.title}"`, 'success')
      setShowCreate(false)
      setForm(EMPTY_JOB)
      navigate(`/jobs/${created.id}`)
    } else {
      addToast('Failed to create job', 'error')
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Hiring Pipeline"
        title="Jobs & Requisitions"
        description="Manage open roles, skill requirements, and drag-and-drop candidate pipelines."
        actions={
          canWrite ? (
            <Button size="lg" className="shadow-glow" onClick={() => setShowCreate(true)}>
              <Plus size={17} />
              Create Job
            </Button>
          ) : undefined
        }
      />

      {/* Filter Bar */}
      <div className="flex flex-col gap-3 rounded-2xl border bg-white p-4 shadow-card sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-1.5">
          {(['all', 'open', 'draft', 'closed'] as const).map((st) => (
            <button
              key={st}
              type="button"
              onClick={() => setStatusFilter(st)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-semibold capitalize transition',
                statusFilter === st
                  ? 'border-brand-600 bg-brand-600 text-white shadow-sm'
                  : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50',
              )}
            >
              {st}
            </button>
          ))}
        </div>

        <div className="relative w-full sm:max-w-xs">
          <Search
            size={15}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title, department, location…"
            className="pl-9 pr-8"
          />
          {search && (
            <button
              type="button"
              onClick={() => setSearch('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-400 hover:bg-slate-100"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {loading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-52 rounded-2xl" />
          ))}
        </div>
      )}

      {!loading && jobs.length === 0 && (
        <div className="rounded-2xl border bg-white p-12 text-center shadow-card">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
            <Briefcase size={22} />
          </div>
          <h3 className="text-base font-semibold text-slate-900">No jobs yet</h3>
          <p className="mt-1 text-sm text-slate-500">
            Create your first job requisition to start tracking candidates across hiring stages.
          </p>
          {canWrite && (
            <Button className="mt-5 shadow-glow" onClick={() => setShowCreate(true)}>
              <Plus size={16} />
              Create First Job
            </Button>
          )}
        </div>
      )}

      {!loading && jobs.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {jobs.map((job) => (
            <Link key={job.id} to={`/jobs/${job.id}`} className="group block h-full">
              <article className="flex h-full flex-col justify-between rounded-2xl border border-stone-200/80 bg-white p-5 shadow-card card-interactive animate-fade-up">
                <div>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge variant={STATUS_BADGE[job.status]} className="capitalize">
                          {job.status}
                        </Badge>
                        {job.min_years != null || job.max_years != null ? (
                          <span className="text-xs font-medium text-slate-500">
                            {job.min_years ?? 0}–{job.max_years ?? '15+'} yrs
                          </span>
                        ) : null}
                      </div>
                      <h3 className="mt-2 truncate text-base font-semibold text-slate-900 group-hover:text-brand-600">
                        {job.title}
                      </h3>
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      {canWrite && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.preventDefault()
                            e.stopPropagation()
                            setDeleteTarget(job)
                          }}
                          title="Delete job"
                          aria-label={`Delete ${job.title}`}
                          className="rounded-lg p-1.5 text-slate-300 transition hover:bg-red-50 hover:text-red-600"
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                      <span className="rounded-lg p-1 text-slate-300 group-hover:bg-brand-50 group-hover:text-brand-600">
                        <ArrowUpRight size={16} />
                      </span>
                    </div>
                  </div>

                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                    {job.department && (
                      <span className="inline-flex items-center gap-1">
                        <Building2 size={12} className="text-slate-400" />
                        {job.department}
                      </span>
                    )}
                    {job.location && (
                      <span className="inline-flex items-center gap-1">
                        <MapPin size={12} className="text-slate-400" />
                        {job.location}
                      </span>
                    )}
                  </div>

                  {job.required_skills.length > 0 && (
                    <div className="mt-4 flex flex-wrap gap-1.5">
                      {job.required_skills.slice(0, 4).map((sk) => (
                        <span
                          key={sk}
                          className="rounded-md border border-violet-200/80 bg-violet-50 px-2 py-0.5 text-[11px] font-medium text-violet-800"
                        >
                          {sk}
                        </span>
                      ))}
                      {job.required_skills.length > 4 && (
                        <span className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600">
                          +{job.required_skills.length - 4}
                        </span>
                      )}
                    </div>
                  )}
                </div>

                <div className="mt-5 flex items-center justify-between border-t border-slate-100 pt-3 text-xs">
                  <span className="inline-flex items-center gap-1.5 font-semibold text-slate-700">
                    <Users size={13} className="text-brand-600" />
                    {job.application_count} candidate{job.application_count === 1 ? '' : 's'}
                  </span>
                  <span className="text-slate-400">Created {formatRelativeDate(job.created_at)}</span>
                </div>
              </article>
            </Link>
          ))}
        </div>
      )}

      {/* Create Job Modal */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm"
            onClick={() => !creating && setShowCreate(false)}
          />
          <form
            onSubmit={handleCreate}
            className="relative max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl border bg-white p-6 shadow-2xl animate-fade-in space-y-4"
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h2 className="text-lg font-semibold text-slate-900">Create Job Requisition</h2>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
              >
                <X size={18} />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="job-title">Job Title *</Label>
                <Input
                  id="job-title"
                  required
                  value={form.title}
                  onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
                  placeholder="Senior AI / Backend Engineer"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="job-dept">Department</Label>
                <Input
                  id="job-dept"
                  value={form.department}
                  onChange={(e) => setForm((p) => ({ ...p, department: e.target.value }))}
                  placeholder="Engineering"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="job-loc">Location</Label>
                <Input
                  id="job-loc"
                  value={form.location}
                  onChange={(e) => setForm((p) => ({ ...p, location: e.target.value }))}
                  placeholder="Mumbai / Hybrid"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="job-min">Min Years</Label>
                <Input
                  id="job-min"
                  type="number"
                  min={0}
                  step="0.5"
                  value={form.min_years ?? ''}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      min_years: e.target.value ? parseFloat(e.target.value) : null,
                    }))
                  }
                  placeholder="2"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="job-max">Max Years</Label>
                <Input
                  id="job-max"
                  type="number"
                  min={0}
                  step="0.5"
                  value={form.max_years ?? ''}
                  onChange={(e) =>
                    setForm((p) => ({
                      ...p,
                      max_years: e.target.value ? parseFloat(e.target.value) : null,
                    }))
                  }
                  placeholder="6"
                />
              </div>

              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="job-status">Status</Label>
                <Select
                  id="job-status"
                  value={form.status}
                  onChange={(e) => setForm((p) => ({ ...p, status: e.target.value as JobStatus }))}
                >
                  <option value="open">Open</option>
                  <option value="draft">Draft</option>
                  <option value="closed">Closed</option>
                </Select>
              </div>

              <div className="space-y-1.5 sm:col-span-2">
                <Label>Required Skills</Label>
                <TagInput
                  value={form.required_skills}
                  onChange={(next) => setForm((p) => ({ ...p, required_skills: next }))}
                  placeholder="Python, FastAPI, PostgreSQL…"
                  tone={{ bg: '#f5f3ff', text: '#5b21b6' }}
                />
              </div>

              <div className="space-y-1.5 sm:col-span-2">
                <Label>Nice-to-have Skills</Label>
                <TagInput
                  value={form.nice_to_have_skills}
                  onChange={(next) => setForm((p) => ({ ...p, nice_to_have_skills: next }))}
                  placeholder="Docker, AWS, React…"
                  tone={{ bg: '#ecfdf5', text: '#065f46' }}
                />
              </div>

              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="job-desc">Job Description</Label>
                <Textarea
                  id="job-desc"
                  rows={4}
                  value={form.description}
                  onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
                  placeholder="Role scope, responsibilities, and team context…"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
              <Button type="button" variant="outline" onClick={() => setShowCreate(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={creating}>
                Create Job
              </Button>
            </div>
          </form>
        </div>
      )}
      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={`Delete "${deleteTarget?.title || 'job'}"?`}
        description="This permanently deletes the job requisition, match scores, and pipeline applications."
        confirmLabel="Delete Job"
        loading={deleting}
        onConfirm={handleConfirmDeleteJob}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
