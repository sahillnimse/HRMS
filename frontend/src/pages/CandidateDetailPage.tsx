import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle,
  Download,
  Edit3,
  LayoutDashboard,
  Network,
  Trash2,
} from 'lucide-react'
import { useCandidates } from '@/hooks/useCandidates'
import { useAddToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/layout/PageHeader'
import { Tabs } from '@/components/ui/Tabs'
import { Button } from '@/components/ui/Button'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { CandidateProfileOverview } from '@/components/CandidateProfileOverview'
import { CandidateNetworkGraph } from '@/components/CandidateNetworkGraph'
import { EditableReview } from '@/components/EditableReview'
import type { CandidateUpdate } from '@/types'

type DetailTab = 'overview' | 'network' | 'edit'

export default function CandidateDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const addToast = useAddToast()
  const { selected, loading, error, getCandidate, updateCandidate, deleteCandidate } =
    useCandidates()

  const [tab, setTab] = useState<DetailTab>('overview')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (id) {
      getCandidate(id)
    }
  }, [id, getCandidate])

  const handleUpdate = async (payload: CandidateUpdate) => {
    if (!id) return
    const updated = await updateCandidate(id, payload)
    if (updated) {
      addToast('Candidate profile updated', 'success')
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
      navigate('/')
    } else {
      addToast('Failed to delete candidate', 'error')
      setConfirmDelete(false)
    }
  }

  const exportJson = () => {
    if (!selected) return
    const blob = new Blob([JSON.stringify(selected, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${selected.full_name.toLowerCase().replace(/\s+/g, '-')}-profile.json`
    a.click()
    URL.revokeObjectURL(url)
    addToast('Profile JSON exported', 'info')
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
        <Button className="mt-6" onClick={() => navigate('/')}>
          Return to Dashboard
        </Button>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        onBack={() => navigate('/')}
        backLabel="All Candidates"
        eyebrow="Candidate Dossier"
        title={selected.full_name}
        description={`${selected.primary_domain} · Detailed profile overview, career trajectory, and interactive skill network.`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={exportJson}>
              <Download size={15} />
              Export JSON
            </Button>
            {tab !== 'edit' && (
              <Button variant="soft" size="sm" onClick={() => setTab('edit')}>
                <Edit3 size={15} />
                Edit Profile
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={() => setConfirmDelete(true)} className="text-red-600 hover:border-red-200 hover:bg-red-50 hover:text-red-700">
              <Trash2 size={15} />
              Delete
            </Button>
          </>
        }
      />

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'overview', label: 'Profile Overview', icon: LayoutDashboard },
          { value: 'network', label: 'Network Graph', icon: Network },
          { value: 'edit', label: 'Edit Details', icon: Edit3 },
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

      <ConfirmDialog
        open={confirmDelete}
        title={`Delete ${selected.full_name}?`}
        description="This permanently removes the candidate profile from the database. This action cannot be undone."
        confirmLabel="Delete Candidate"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  )
}
