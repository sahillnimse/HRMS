import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  ArrowUpRight,
  Briefcase,
  Clock,
  MessageSquare,
  Send,
  Shield,
  Trash2,
} from 'lucide-react'
import { api, getErrorMessage } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useAddToast } from '@/components/ui/Toast'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Textarea } from '@/components/ui/Textarea'
import { TagInput } from '@/components/ui/TagInput'
import { formatRelativeDate } from '@/lib/utils'
import type { ActivityTimelineItem, ApplicationItem, CandidateNote } from '@/types'

interface CandidateNotesAndActivityProps {
  candidateId: string
  refreshKey?: number
}

export function CandidateNotesAndActivity({
  candidateId,
  refreshKey = 0,
}: CandidateNotesAndActivityProps) {
  const { user, canWrite, isAdmin } = useAuth()
  const addToast = useAddToast()

  const [applications, setApplications] = useState<ApplicationItem[]>([])
  const [notes, setNotes] = useState<CandidateNote[]>([])
  const [activity, setActivity] = useState<ActivityTimelineItem[]>([])
  const [loading, setLoading] = useState(true)

  const [noteBody, setNoteBody] = useState('')
  const [noteTags, setNoteTags] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [appsRes, notesRes, actRes] = await Promise.all([
        api.get<ApplicationItem[]>(`/candidates/${candidateId}/applications`),
        api.get<CandidateNote[]>(`/candidates/${candidateId}/notes`),
        api.get<ActivityTimelineItem[]>(`/candidates/${candidateId}/activity`),
      ])
      setApplications(appsRes.data)
      setNotes(notesRes.data)
      setActivity(actRes.data)
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to load notes & activity'), 'error')
    } finally {
      setLoading(false)
    }
  }, [candidateId, addToast])

  useEffect(() => {
    void loadAll()
  }, [loadAll, refreshKey])

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!noteBody.trim()) return
    setSubmitting(true)
    try {
      await api.post(`/candidates/${candidateId}/notes`, {
        body: noteBody.trim(),
        tags: noteTags,
      })
      setNoteBody('')
      setNoteTags([])
      addToast('Note added', 'success')
      await loadAll()
    } catch (err) {
      addToast(getErrorMessage(err, 'Could not add note'), 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteNote = async (noteId: string) => {
    try {
      await api.delete(`/candidates/${candidateId}/notes/${noteId}`)
      addToast('Note deleted', 'info')
      await loadAll()
    } catch (err) {
      addToast(getErrorMessage(err, 'Could not delete note'), 'error')
    }
  }

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-12 animate-fade-in">
      {/* Left 7 Cols: Active Applications + Notes */}
      <div className="space-y-6 lg:col-span-7">
        {/* Active Job Applications */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Briefcase size={16} className="text-brand-600" />
                <CardTitle>Active Job Pipelines</CardTitle>
              </div>
              <Badge variant="secondary">{applications.length}</Badge>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="skeleton h-16 w-full rounded-xl" />
            ) : applications.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500">
                Not yet added to any job requisition.
              </p>
            ) : (
              <div className="space-y-2">
                {applications.map((app) => (
                  <Link
                    key={app.id}
                    to={`/jobs/${app.job_id}`}
                    className="flex items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-slate-50/50 px-4 py-3 transition hover:border-brand-200 hover:bg-white"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {app.job_title || 'Job Requisition'}
                      </p>
                      <p className="text-xs text-slate-500">
                        {app.job_department || 'General'} · Updated{' '}
                        {formatRelativeDate(app.stage_changed_at)}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Badge
                        variant={
                          app.stage === 'hired'
                            ? 'success'
                            : app.stage === 'rejected'
                              ? 'destructive'
                              : 'brand'
                        }
                        className="capitalize"
                      >
                        {app.stage}
                      </Badge>
                      <ArrowUpRight size={14} className="text-slate-400" />
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Notes */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <MessageSquare size={16} className="text-violet-600" />
                <CardTitle>Recruiter Notes</CardTitle>
              </div>
              <Badge variant="secondary">{notes.length}</Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {canWrite && (
              <form
                onSubmit={handleAddNote}
                className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/50 p-4"
              >
                <Textarea
                  rows={3}
                  value={noteBody}
                  onChange={(e) => setNoteBody(e.target.value)}
                  placeholder="Log screening feedback, interview observations, salary expectations…"
                />
                <TagInput
                  value={noteTags}
                  onChange={setNoteTags}
                  placeholder="Add tags (e.g. screening, strong-python, notice-period)…"
                  tone={{ bg: '#eef2ff', text: '#3730a3' }}
                />
                <div className="flex justify-end">
                  <Button type="submit" size="sm" loading={submitting} disabled={!noteBody.trim()}>
                    <Send size={14} />
                    Add Note
                  </Button>
                </div>
              </form>
            )}

            {loading ? (
              <div className="space-y-2">
                <div className="skeleton h-20 rounded-xl" />
                <div className="skeleton h-20 rounded-xl" />
              </div>
            ) : notes.length === 0 ? (
              <p className="text-sm text-slate-500">No notes yet for this candidate.</p>
            ) : (
              <div className="space-y-3">
                {notes.map((n) => {
                  const canDelete = isAdmin || (user?.id && n.author_id === user.id)
                  return (
                    <div
                      key={n.id}
                      className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <p className="text-xs font-semibold text-slate-900">
                            {n.author_name || 'Team Member'}
                          </p>
                          <p className="text-[11px] text-slate-400">
                            {formatRelativeDate(n.created_at)}
                          </p>
                        </div>
                        {canDelete && (
                          <button
                            type="button"
                            onClick={() => void handleDeleteNote(n.id)}
                            className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
                            aria-label="Delete note"
                          >
                            <Trash2 size={13} />
                          </button>
                        )}
                      </div>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                        {n.body}
                      </p>
                      {n.tags.length > 0 && (
                        <div className="mt-2.5 flex flex-wrap gap-1">
                          {n.tags.map((t) => (
                            <Badge key={t} variant="brand" className="text-[11px]">
                              #{t}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Right 5 Cols: Activity & Audit Timeline */}
      <div className="lg:col-span-5">
        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Activity size={16} className="text-sky-600" />
              <CardTitle>Activity & Audit Timeline</CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3">
                {[0, 1, 2, 3].map((i) => (
                  <div key={i} className="skeleton h-14 rounded-xl" />
                ))}
              </div>
            ) : activity.length === 0 ? (
              <p className="text-sm text-slate-500">No recorded activity yet.</p>
            ) : (
              <ol className="relative space-y-4 pl-6 before:absolute before:bottom-2 before:left-[9px] before:top-2 before:w-px before:bg-slate-200">
                {activity.map((item) => {
                  const Icon =
                    item.kind === 'stage_change'
                      ? Briefcase
                      : item.kind === 'note'
                        ? MessageSquare
                        : Shield
                  const dotTone =
                    item.kind === 'stage_change'
                      ? 'bg-brand-600 text-white'
                      : item.kind === 'note'
                        ? 'bg-violet-500 text-white'
                        : 'bg-slate-200 text-slate-600'
                  return (
                    <li key={item.id} className="relative">
                      <span
                        className={`absolute -left-6 top-1 flex h-5 w-5 items-center justify-center rounded-full ring-2 ring-white ${dotTone}`}
                      >
                        <Icon size={10} />
                      </span>
                      <div className="rounded-xl border border-slate-100 bg-slate-50/70 px-3.5 py-2.5">
                        <p className="text-xs font-medium leading-5 text-slate-800">
                          {item.summary}
                        </p>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                          {item.actor_name && (
                            <span className="font-medium text-slate-500">{item.actor_name}</span>
                          )}
                          <span className="inline-flex items-center gap-1">
                            <Clock size={10} />
                            {formatRelativeDate(item.timestamp)}
                          </span>
                        </div>
                      </div>
                    </li>
                  )
                })}
              </ol>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
