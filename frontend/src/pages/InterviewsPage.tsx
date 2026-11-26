import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Calendar, Download, FileText, Mail, Plus, Star } from 'lucide-react'
import { api, downloadBlobFile, getErrorMessage } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { useAddToast } from '@/components/ui/Toast'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Tabs } from '@/components/ui/Tabs'
import type { EmailTemplate, InterviewItem, ScorecardTemplate } from '@/types'

type PageTab = 'mine' | 'scorecard-templates' | 'email-templates'

function formatIST(iso: string): string {
  try {
    return (
      new Intl.DateTimeFormat('en-IN', {
        dateStyle: 'medium',
        timeStyle: 'short',
        timeZone: 'Asia/Kolkata',
      }).format(new Date(iso)) + ' IST'
    )
  } catch {
    return iso
  }
}

export default function InterviewsPage() {
  const { isAdmin } = useAuth()
  const { blindMode } = useBlindMode()
  const addToast = useAddToast()

  const [tab, setTab] = useState<PageTab>('mine')
  const [interviews, setInterviews] = useState<InterviewItem[]>([])
  const [scTemplates, setScTemplates] = useState<ScorecardTemplate[]>([])
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([])
  const [loading, setLoading] = useState(true)

  // Admin quick email template editor
  const [editingTpl, setEditingTpl] = useState<EmailTemplate | null>(null)
  const [newTplName, setNewTplName] = useState('')

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [ivRes, scRes, emRes] = await Promise.all([
        api.get<InterviewItem[]>('/interviews/mine', {
          params: blindMode ? { blind: true } : undefined,
        }),
        api.get<ScorecardTemplate[]>('/scorecard-templates/'),
        api.get<EmailTemplate[]>('/email-templates/'),
      ])
      setInterviews(ivRes.data)
      setScTemplates(scRes.data)
      setEmailTemplates(emRes.data)
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to load interviews'), 'error')
    } finally {
      setLoading(false)
    }
  }, [blindMode, addToast])

  useEffect(() => {
    void loadAll()
  }, [loadAll])

  const handleSaveEmailTpl = async () => {
    if (!editingTpl) return
    try {
      await api.put(`/email-templates/${editingTpl.id}`, {
        subject: editingTpl.subject,
        body: editingTpl.body,
        auto_send: editingTpl.auto_send,
      })
      addToast(`Updated template "${editingTpl.key}"`, 'success')
      setEditingTpl(null)
      void loadAll()
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to save template'), 'error')
    }
  }

  const handleCreateScorecardTpl = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newTplName.trim()) return
    try {
      await api.post('/scorecard-templates/', {
        name: newTplName.trim(),
        scale: 5,
        competencies: [
          { name: 'Role & Technical Depth', description: 'Core role skills', weight: 0.4 },
          { name: 'Problem Solving', description: 'Analytical & practical rigor', weight: 0.35 },
          { name: 'Collaboration', description: 'Teamwork & clarity', weight: 0.25 },
        ],
      })
      setNewTplName('')
      addToast('Scorecard template created', 'success')
      void loadAll()
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to create template'), 'error')
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Interview Workflow"
        title="Interviews & Templates"
        description="View your upcoming interviews in Asia/Kolkata (IST), download .ics calendar invites, and manage hiring scorecard & email templates."
      />

      <Tabs
        value={tab}
        onChange={setTab}
        items={[
          { value: 'mine', label: `My Interviews (${interviews.length})`, icon: Calendar },
          ...(isAdmin
            ? [
                {
                  value: 'scorecard-templates' as const,
                  label: `Scorecard Templates (${scTemplates.length})`,
                  icon: Star,
                },
                {
                  value: 'email-templates' as const,
                  label: `Email Templates (${emailTemplates.length})`,
                  icon: Mail,
                },
              ]
            : []),
        ]}
      />

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="skeleton h-24 rounded-2xl" />
          ))}
        </div>
      ) : tab === 'mine' ? (
        interviews.length === 0 ? (
          <Card>
            <CardContent className="p-10 text-center text-sm text-slate-500">
              No interviews assigned to you yet. Drag a candidate to the Interview stage on a Job
              Kanban board or schedule from a candidate profile.
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {interviews.map((iv) => (
              <Card key={iv.id} className="card-interactive">
                <CardContent className="flex flex-col gap-3 p-5 sm:flex-row sm:items-center sm:justify-between">
                  <div className="space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-display text-sm font-bold text-slate-900">
                        {iv.round_name}
                      </span>
                      <Badge variant="brand" className="capitalize">
                        {iv.mode}
                      </Badge>
                      <Badge variant="secondary" className="capitalize">
                        {iv.status}
                      </Badge>
                      {iv.scorecard_aggregate.count > 0 && (
                        <Badge variant="success">
                          ★ {iv.scorecard_aggregate.average_rating}/{iv.scorecard_aggregate.scale} (
                          {iv.scorecard_aggregate.count})
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-slate-600">
                      {iv.candidate_name || 'Candidate'}
                      {iv.job_title ? ` · ${iv.job_title}` : ''} · {formatIST(iv.scheduled_at)} (
                      {iv.duration_minutes}m)
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() =>
                        void downloadBlobFile(
                          `/interviews/${iv.id}/ics`,
                          { blind: blindMode },
                          `interview-${iv.id.slice(0, 8)}.ics`,
                        )
                      }
                    >
                      <Download size={13} />
                      .ics Invite
                    </Button>
                    {iv.candidate_id && (
                      <Button asChild size="sm">
                        <Link to={`/candidates/${iv.candidate_id}`}>Open Profile &amp; Scorecard</Link>
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )
      ) : tab === 'scorecard-templates' ? (
        <div className="space-y-4">
          <form onSubmit={handleCreateScorecardTpl} className="flex gap-2">
            <Input
              value={newTplName}
              onChange={(e) => setNewTplName(e.target.value)}
              placeholder="New scorecard template name (e.g. Staff Backend Loop)…"
              className="max-w-md"
            />
            <Button type="submit" size="sm">
              <Plus size={14} />
              Create Template
            </Button>
          </form>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {scTemplates.map((tpl) => (
              <Card key={tpl.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm">{tpl.name}</CardTitle>
                    <Badge variant="secondary">Scale 1–{tpl.scale}</Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-1.5 text-xs text-slate-600">
                  {tpl.competencies.map((c) => (
                    <div key={c.name} className="flex justify-between gap-2">
                      <span className="font-medium text-slate-800">{c.name}</span>
                      <span>Weight {Math.round(c.weight * 100)}%</span>
                    </div>
                  ))}
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {emailTemplates.map((tpl) => {
            const isEditing = editingTpl?.id === tpl.id
            const isRejection = tpl.key.toLowerCase().includes('reject')
            return (
              <Card key={tpl.id}>
                <CardContent className="p-5 space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <FileText size={15} className="text-brand-600" />
                      <span className="font-mono text-xs font-bold text-slate-900">{tpl.key}</span>
                      {isRejection && (
                        <Badge variant="warning">Manual confirmation required</Badge>
                      )}
                    </div>
                    {!isEditing && (
                      <Button variant="outline" size="sm" onClick={() => setEditingTpl({ ...tpl })}>
                        Edit
                      </Button>
                    )}
                  </div>

                  {isEditing && editingTpl ? (
                    <div className="space-y-2.5">
                      <Input
                        value={editingTpl.subject}
                        onChange={(e) =>
                          setEditingTpl((p) => (p ? { ...p, subject: e.target.value } : p))
                        }
                      />
                      <Textarea
                        rows={5}
                        value={editingTpl.body}
                        onChange={(e) =>
                          setEditingTpl((p) => (p ? { ...p, body: e.target.value } : p))
                        }
                      />
                      {!isRejection && (
                        <label className="inline-flex items-center gap-2 text-xs text-slate-600">
                          <input
                            type="checkbox"
                            checked={editingTpl.auto_send}
                            onChange={(e) =>
                              setEditingTpl((p) => (p ? { ...p, auto_send: e.target.checked } : p))
                            }
                          />
                          Enable automatic stage-change email (OFF by default)
                        </label>
                      )}
                      <div className="flex justify-end gap-2">
                        <Button variant="ghost" size="sm" onClick={() => setEditingTpl(null)}>
                          Cancel
                        </Button>
                        <Button size="sm" onClick={() => void handleSaveEmailTpl()}>
                          Save Template
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <div className="text-xs text-slate-600 space-y-1">
                      <p className="font-semibold text-slate-800">{tpl.subject}</p>
                      <p className="whitespace-pre-line line-clamp-3">{tpl.body}</p>
                    </div>
                  )}
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
