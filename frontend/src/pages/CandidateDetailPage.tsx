import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  Briefcase,
  Download,
  Edit3,
  FileText,
  LayoutDashboard,
  MessageSquare,
  Network,
  Trash2,
  X,
} from 'lucide-react'
import { useCandidates } from '@/hooks/useCandidates'
import { useJobs } from '@/hooks/useJobs'
import { useAuth } from '@/contexts/AuthContext'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { useAddToast } from '@/components/ui/Toast'
import { api, downloadBlobFile, fetchResumeBlob, getErrorMessage } from '@/lib/api'
import { getSourceFilename, getStoredFilename } from '@/lib/profile'
import { PageHeader } from '@/components/layout/PageHeader'
import { Tabs } from '@/components/ui/Tabs'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { CandidateProfileOverview } from '@/components/CandidateProfileOverview'
import { CandidateNetworkGraph } from '@/components/CandidateNetworkGraph'
import { CandidateNotesAndActivity } from '@/components/CandidateNotesAndActivity'
import { EditableReview } from '@/components/EditableReview'
import { ResumePreview } from '@/components/ResumePreview'
import type { ApplicationItem, CandidateResponse, CandidateUpdate } from '@/types'

type DetailTab = 'overview' | 'network' | 'activity' | 'resume' | 'edit'

export default function CandidateDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const addToast = useAddToast()
  const { canWrite } = useAuth()
  const { blindMode } = useBlindMode()
  const { selected, loading, error, getCandidate, updateCandidate, deleteCandidate } =
    useCandidates()
  const { jobs, fetchJobs, addApplication } = useJobs()

  const [tab, setTab] = useState<DetailTab>('overview')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [openingCv, setOpeningCv] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportingPdf, setExportingPdf] = useState(false)

  const [showAddToJob, setShowAddToJob] = useState(false)
  const [candidateApps, setCandidateApps] = useState<ApplicationItem[]>([])
  const [addingJobId, setAddingJobId] = useState<string | null>(null)
  const [activityRefresh, setActivityRefresh] = useState(0)

  useEffect(() => {
    if (id) {
      void getCandidate(id, { blind: blindMode })
    }
  }, [id, blindMode, getCandidate])

  useEffect(() => {
    if (blindMode && tab === 'resume') {
      setTab('overview')
    }
  }, [blindMode, tab])

  useEffect(() => {
    if (showAddToJob && id) {
      void fetchJobs()
      api
        .get<ApplicationItem[]>(`/candidates/${id}/applications`)
        .then((res) => setCandidateApps(res.data))
        .catch(() => {})
    }
  }, [showAddToJob, id, fetchJobs])

  const handleOpenCv = async () => {
    if (!selected?.resume_file_id) return
    try {
      setOpeningCv(true)
      const blob = await fetchResumeBlob(selected.resume_file_id, false)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      addToast('Could not open saved resume file', 'error')
    } finally {
      setOpeningCv(false)
    }
  }

  const handleUpdate = async (payload: CandidateUpdate) => {
    if (!id) return
    const updated = await updateCandidate(id, payload)
    if (updated) {
      addToast('Candidate profile updated', 'success')
      setActivityRefresh((n) => n + 1)
      setTab('overview')
    } else {
      addToast('Could not update candidate profile', 'error')
    }
  }

  const handleDelete = async () => {
    if (!id) return
    setDeleting(true)
    const ok = await deleteCandidate(id)
    setDeleting(false)
    if (ok) {
      addToast('Candidate deleted', 'success')
      navigate('/candidates')
    } else {
      addToast('Failed to delete candidate', 'error')
      setConfirmDelete(false)
    }
  }

  const handleAddToJob = async (jobId: string, jobTitle: string) => {
    if (!id) return
    setAddingJobId(jobId)
    const created = await addApplication(id, jobId, 'applied')
    setAddingJobId(null)
    if (created) {
      setCandidateApps((prev) => [created, ...prev])
      setActivityRefresh((n) => n + 1)
      addToast(`Added to "${jobTitle}"`, 'success')
    } else {
      addToast('Could not add candidate to job', 'error')
    }
  }

  const exportJson = async () => {
    if (!id || !selected) return
    try {
      setExporting(true)
      const res = await api.get<CandidateResponse>(`/candidates/${id}/export`, {
        params: blindMode ? { blind: true } : undefined,
      })
      const blob = new Blob([JSON.stringify(res.data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${selected.full_name.toLowerCase().replace(/\s+/g, '-')}-profile.json`
      a.click()
      URL.revokeObjectURL(url)
      setActivityRefresh((n) => n + 1)
      addToast('Profile JSON exported', 'info')
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to export JSON'), 'error')
    } finally {
      setExporting(false)
    }
  }

  const exportPdf = async () => {
    if (!id || !selected) return
    try {
      setExportingPdf(true)
      await downloadBlobFile(
        `/candidates/${id}/export/pdf`,
        { blind: blindMode },
        `${selected.full_name.toLowerCase().replace(/\s+/g, '-')}-brief.pdf`,
      )
      setActivityRefresh((n) => n + 1)
      addToast(blindMode ? 'Blind PDF brief exported' : 'One-page PDF exported', 'success')
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to export PDF'), 'error')
    } finally {
      setExportingPdf(false)
    }
  }

  if (loading && !selected) {
    return (
      <div className="space-y-6">
        <div className="skeleton h-10 w-64" />
        <div className="skeleton h-52 w-full rounded-2xl" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-28 rounded-2xl" />
          ))}
        </div>
        <div className="skeleton h-96 w-full rounded-2xl" />
      </div>
    )
  }

  if (!selected) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border bg-white p-10 text-center shadow-card">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600">
          <AlertTriangle size={22} />
        </div>
        <h2 className="text-lg font-semibold text-slate-900">Candidate not found</h2>
        <p className="mt-1 text-sm text-slate-500">
          {error || 'This candidate profile may have been deleted or does not exist.'}
        </p>
        <Button className="mt-6" onClick={() => navigate('/candidates')}>
          Return to Candidates
        </Button>
      </div>
    )
  }

  const appliedJobIds = new Set(candidateApps.map((a) => a.job_id))

  return (
    <div className="space-y-6">
      <PageHeader
        onBack={() => navigate('/candidates')}
        backLabel="All Candidates"
        eyebrow="Candidate Dossier"
        title={selected.full_name}
        description={`${selected.primary_domain} · Detailed profile overview, career trajectory, skill network, notes & hiring pipeline activity.`}
        actions={
          <>
            {canWrite && (
              <Button size="sm" onClick={() => setShowAddToJob(true)} className="shadow-glow">
                <Briefcase size={15} />
                Add to Job
              </Button>
            )}
            {!blindMode && selected.resume_file_id && (
              <Button variant="outline" size="sm" onClick={handleOpenCv} loading={openingCv}>
                <FileText size={15} />
                View Saved CV
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={exportPdf} loading={exportingPdf}>
              <Download size={15} />
              {blindMode ? 'Blind PDF' : 'Export PDF'}
            </Button>
            <Button variant="outline" size="sm" onClick={exportJson} loading={exporting}>
              <Download size={15} />
              JSON
            </Button>
            {canWrite && tab !== 'edit' && (
              <Button variant="soft" size="sm" onClick={() => setTab('edit')}>
                <Edit3 size={15} />
                Edit Profile
              </Button>
            )}
            {canWrite && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setConfirmDelete(true)}
                className="text-red-600 hover:border-red-200 hover:bg-red-50 hover:text-red-700"
              >
                <Trash2 size={15} />
                Delete
              </Button>
            )}
          </>
        }
      />

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'overview', label: 'Profile Overview', icon: LayoutDashboard },
          { value: 'network', label: 'Network Graph', icon: Network },
          { value: 'activity', label: 'Notes & Activity', icon: MessageSquare },
          ...(!blindMode && selected.resume_file_id
            ? [{ value: 'resume' as const, label: 'Saved Resume / CV', icon: FileText }]
            : []),
          ...(canWrite && !blindMode
            ? [{ value: 'edit' as const, label: 'Edit Details', icon: Edit3 }]
            : []),
        ]}
      />

      {tab === 'overview' && (
        <CandidateProfileOverview
          profile={selected}
          rawParsedData={selected.raw_parsed_data}
          resumeFileId={selected.resume_file_id}
          createdAt={selected.created_at}
          showGraph
        />
      )}

      {tab === 'network' && (
        <CandidateNetworkGraph
          profile={selected}
          height={640}
          title={`${selected.full_name} — Full Talent Network`}
        />
      )}

      {tab === 'activity' && (
        <CandidateNotesAndActivity candidateId={selected.id} refreshKey={activityRefresh} />
      )}

      {tab === 'resume' && selected.resume_file_id && (
        <ResumePreview
          resumeFileId={selected.resume_file_id}
          originalFilename={getSourceFilename(selected.raw_parsed_data)}
          storedFilename={getStoredFilename(selected.raw_parsed_data)}
          previewHeightClass="h-[720px]"
        />
      )}

      {tab === 'edit' && (
        <EditableReview
          parsedData={selected}
          resumeFileId={selected.resume_file_id}
          onSave={handleUpdate}
          onCancel={() => setTab('overview')}
          saving={loading}
          submitLabel="Save Changes"
          cancelLabel="Cancel"
        />
      )}

      {/* Add to Job Modal */}
      {showAddToJob && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-slate-900/30 backdrop-blur-sm"
            onClick={() => setShowAddToJob(false)}
          />
          <div className="relative flex max-h-[85vh] w-full max-w-lg flex-col rounded-2xl border bg-white p-6 shadow-2xl animate-fade-in">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <h3 className="text-base font-semibold text-slate-900">
                Add {selected.full_name} to a Job
              </h3>
              <button
                type="button"
                onClick={() => setShowAddToJob(false)}
                className="rounded-lg p-1 text-slate-400 hover:bg-slate-100"
              >
                <X size={18} />
              </button>
            </div>

            <div className="mt-4 flex-1 space-y-2 overflow-y-auto pr-1">
              {jobs.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="text-sm text-slate-500">No jobs created yet.</p>
                  <Button
                    size="sm"
                    className="mt-3"
                    onClick={() => {
                      setShowAddToJob(false)
                      navigate('/jobs')
                    }}
                  >
                    Go to Jobs
                  </Button>
                </div>
              ) : (
                jobs.map((job) => {
                  const alreadyIn = appliedJobIds.has(job.id)
                  return (
                    <div
                      key={job.id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-slate-200/80 p-3.5"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-semibold text-slate-900">
                            {job.title}
                          </p>
                          <Badge variant="secondary" className="capitalize text-[10px]">
                            {job.status}
                          </Badge>
                        </div>
                        <p className="truncate text-xs text-slate-500">
                          {[job.department, job.location].filter(Boolean).join(' · ') || 'General'}
                        </p>
                      </div>
                      {alreadyIn ? (
                        <Badge variant="brand">Already added</Badge>
                      ) : (
                        <Button
                          size="sm"
                          loading={addingJobId === job.id}
                          onClick={() => void handleAddToJob(job.id, job.title)}
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
        title={`Delete ${selected.full_name}?`}
        description="This permanently removes the candidate profile and resume file from storage. This action cannot be undone."
        confirmLabel="Delete Candidate"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  )
}
