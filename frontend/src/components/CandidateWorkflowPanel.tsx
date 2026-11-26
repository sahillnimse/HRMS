import { useCallback, useEffect, useState } from 'react'
import {
  Briefcase,
  Calendar,
  CheckCircle2,
  Download,
  Lock,
  Mail,
  Plus,
  Send,
  Star,
  Wallet,
} from 'lucide-react'
import { api, downloadBlobFile, getErrorMessage } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { blindCandidateLabel, useBlindMode } from '@/contexts/BlindModeContext'
import { useAddToast } from '@/components/ui/Toast'
import { formatCtc } from '@/lib/profile'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Textarea } from '@/components/ui/Textarea'
import { ScheduleInterviewModal } from '@/components/ScheduleInterviewModal'
import { formatRelativeDate } from '@/lib/utils'
import type {
  ApplicationItem,
  EmailLogItem,
  EmailPreview,
  EmailTemplate,
  InterviewItem,
  InterviewScorecards,
  OfferItem,
  ScorecardAggregate,
  ScorecardTemplate,
} from '@/types'

interface CandidateWorkflowPanelProps {
  candidateId: string
  candidateName: string
  candidateEmail: string | null
  noticePeriodDays?: number | null
  onActivityChange?: () => void
}

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

export function CandidateWorkflowPanel({
  candidateId,
  candidateName,
  candidateEmail,
  onActivityChange,
}: CandidateWorkflowPanelProps) {
  const { canWrite } = useAuth()
  const { blindMode } = useBlindMode()
  const addToast = useAddToast()

  const [applications, setApplications] = useState<ApplicationItem[]>([])
  const [selectedAppId, setSelectedAppId] = useState<string>('')
  const [interviews, setInterviews] = useState<InterviewItem[]>([])
  const [offers, setOffers] = useState<OfferItem[]>([])
  const [scorecardSummary, setScorecardSummary] = useState<ScorecardAggregate | null>(null)
  const [scorecardTemplates, setScorecardTemplates] = useState<ScorecardTemplate[]>([])
  const [emailTemplates, setEmailTemplates] = useState<EmailTemplate[]>([])
  const [emailLogs, setEmailLogs] = useState<EmailLogItem[]>([])
  const [loading, setLoading] = useState(true)

  // Modals / inline panels
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const [activeScorecardIvId, setActiveScorecardIvId] = useState<string | null>(null)
  const [ivScorecards, setIvScorecards] = useState<InterviewScorecards | null>(null)
  const [ratings, setRatings] = useState<Record<string, number>>({})
  const [recommendation, setRecommendation] = useState<'strong_no' | 'no' | 'yes' | 'strong_yes'>('yes')
  const [comments, setComments] = useState('')
  const [submittingSc, setSubmittingSc] = useState(false)

  // Offer form
  const [showOfferForm, setShowOfferForm] = useState(false)
  const [offerCtc, setOfferCtc] = useState('')
  const [offerCurrency, setOfferCurrency] = useState('INR')
  const [offerStatus, setOfferStatus] = useState<'draft' | 'extended' | 'accepted' | 'declined' | 'withdrawn'>('draft')
  const [offerNotes, setOfferNotes] = useState('')
  const [savingOffer, setSavingOffer] = useState(false)

  // Email composer
  const [selectedTplKey, setSelectedTplKey] = useState('')
  const [emailPreview, setEmailPreview] = useState<EmailPreview | null>(null)
  const [confirmRejection, setConfirmRejection] = useState(false)
  const [sendingEmail, setSendingEmail] = useState(false)

  const loadBase = useCallback(async () => {
    setLoading(true)
    try {
      const [appsRes, sumRes, tplRes, emailTplRes, emailLogRes] = await Promise.all([
        api.get<ApplicationItem[]>(`/candidates/${candidateId}/applications`),
        api.get<ScorecardAggregate>(`/candidates/${candidateId}/scorecard-summary`),
        api.get<ScorecardTemplate[]>('/scorecard-templates/'),
        api.get<EmailTemplate[]>('/email-templates/'),
        api.get<EmailLogItem[]>(`/candidates/${candidateId}/emails`),
      ])
      setApplications(appsRes.data)
      if (appsRes.data.length > 0) {
        setSelectedAppId((prev) => prev || appsRes.data[0].id)
      }
      setScorecardSummary(sumRes.data)
      setScorecardTemplates(tplRes.data)
      setEmailTemplates(emailTplRes.data)
      if (emailTplRes.data.length > 0 && !selectedTplKey) {
        setSelectedTplKey(emailTplRes.data[0].key)
      }
      setEmailLogs(emailLogRes.data)
    } finally {
      setLoading(false)
    }
  }, [candidateId, selectedTplKey])

  useEffect(() => {
    void loadBase()
  }, [loadBase])

  const loadAppDetails = useCallback(async (appId: string) => {
    if (!appId) {
      setInterviews([])
      setOffers([])
      return
    }
    const ivReq = api.get<InterviewItem[]>(`/applications/${appId}/interviews`, {
      params: blindMode ? { blind: true } : undefined,
    })
    const offReq = canWrite
      ? api.get<OfferItem[]>(`/applications/${appId}/offers`)
      : Promise.resolve({ data: [] as OfferItem[] })
    const [ivRes, offRes] = await Promise.all([ivReq, offReq])
    setInterviews(ivRes.data)
    setOffers(offRes.data)
  }, [blindMode, canWrite])

  useEffect(() => {
    if (selectedAppId) void loadAppDetails(selectedAppId)
  }, [selectedAppId, loadAppDetails])

  const openScorecardPanel = async (interviewId: string) => {
    if (activeScorecardIvId === interviewId) {
      setActiveScorecardIvId(null)
      return
    }
    setActiveScorecardIvId(interviewId)
    try {
      const res = await api.get<InterviewScorecards>(`/interviews/${interviewId}/scorecards`)
      setIvScorecards(res.data)
      const defaultTpl = scorecardTemplates[0]
      if (defaultTpl) {
        const init: Record<string, number> = {}
        defaultTpl.competencies.forEach((c) => {
          init[c.name] = 4
        })
        setRatings(init)
      }
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to load scorecards'), 'error')
    }
  }

  const handleSubmitScorecard = async (interviewId: string) => {
    setSubmittingSc(true)
    try {
      await api.post(`/interviews/${interviewId}/scorecards`, {
        template_id: scorecardTemplates[0]?.id ?? null,
        ratings,
        recommendation,
        comments,
      })
      addToast('Scorecard submitted', 'success')
      setComments('')
      const refreshed = await api.get<InterviewScorecards>(`/interviews/${interviewId}/scorecards`)
      setIvScorecards(refreshed.data)
      void loadBase()
      void loadAppDetails(selectedAppId)
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to submit scorecard'), 'error')
    } finally {
      setSubmittingSc(false)
    }
  }

  const handleCreateOffer = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedAppId || !offerCtc) return
    setSavingOffer(true)
    try {
      await api.post(`/applications/${selectedAppId}/offers`, {
        offered_ctc: parseFloat(offerCtc),
        currency: offerCurrency,
        status: offerStatus,
        notes: offerNotes,
      })
      addToast('Offer saved', 'success')
      setShowOfferForm(false)
      setOfferCtc('')
      setOfferNotes('')
      void loadAppDetails(selectedAppId)
      void loadBase()
      onActivityChange?.()
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to save offer'), 'error')
    } finally {
      setSavingOffer(false)
    }
  }

  const handleOfferStatus = async (offerId: string, nextStatus: string) => {
    try {
      await api.patch(`/offers/${offerId}`, { status: nextStatus })
      addToast(`Offer marked as ${nextStatus}`, 'success')
      void loadAppDetails(selectedAppId)
      void loadBase()
      onActivityChange?.()
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to update offer'), 'error')
    }
  }

  const handlePreviewEmail = async () => {
    if (!selectedTplKey) return
    try {
      const res = await api.post<EmailPreview>('/emails/preview', {
        candidate_id: candidateId,
        application_id: selectedAppId || null,
        template_key: selectedTplKey,
      })
      setEmailPreview(res.data)
      setConfirmRejection(false)
    } catch (err) {
      addToast(getErrorMessage(err, 'Could not preview email'), 'error')
    }
  }

  const handleSendEmail = async () => {
    if (!emailPreview) return
    const isRej = (selectedTplKey || '').toLowerCase().includes('reject')
    if (isRej && !confirmRejection) {
      addToast('Please confirm before sending a rejection email.', 'error')
      return
    }
    setSendingEmail(true)
    try {
      await api.post('/emails/send', {
        candidate_id: candidateId,
        application_id: selectedAppId || null,
        template_key: selectedTplKey || null,
        subject: emailPreview.subject,
        body: emailPreview.body,
        confirm_rejection: confirmRejection,
      })
      addToast('Email logged and dispatched', 'success')
      setEmailPreview(null)
      setConfirmRejection(false)
      void loadBase()
      onActivityChange?.()
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to send email'), 'error')
    } finally {
      setSendingEmail(false)
    }
  }

  const activeApp = applications.find((a) => a.id === selectedAppId) ?? null
  const displayName = blindMode ? blindCandidateLabel(candidateId) : candidateName

  if (loading) {
    return <div className="skeleton h-64 w-full rounded-2xl" />
  }

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Scorecard Aggregate Strip */}
      {scorecardSummary && scorecardSummary.count > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-brand-200/80 bg-brand-50/50 px-5 py-3.5">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand-600 text-white">
              <Star size={16} />
            </span>
            <div>
              <p className="text-xs font-bold text-slate-900">
                Interview Scorecard Aggregate ({scorecardSummary.count} submitted)
              </p>
              <p className="text-xs text-slate-600">
                Average:{' '}
                <span className="font-bold text-brand-700">
                  {scorecardSummary.average_rating ?? '—'} / {scorecardSummary.scale}
                </span>
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5 text-[11px]">
            <Badge variant="success">Strong Yes: {scorecardSummary.recommendations.strong_yes ?? 0}</Badge>
            <Badge variant="brand">Yes: {scorecardSummary.recommendations.yes ?? 0}</Badge>
            <Badge variant="warning">No: {scorecardSummary.recommendations.no ?? 0}</Badge>
            <Badge variant="destructive">Strong No: {scorecardSummary.recommendations.strong_no ?? 0}</Badge>
          </div>
        </div>
      )}

      {/* Application selector */}
      {applications.length === 0 ? (
        <Card>
          <CardContent className="p-8 text-center text-sm text-slate-500">
            Add this candidate to a job requisition first to schedule interviews, submit scorecards,
            or manage offers.
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-stone-200/80 bg-white px-4 py-3 shadow-card">
            <div className="flex items-center gap-2">
              <Briefcase size={15} className="text-brand-600" />
              <span className="text-xs font-semibold text-slate-600">Application:</span>
              <Select
                value={selectedAppId}
                onChange={(e) => setSelectedAppId(e.target.value)}
                className="h-9 w-64 text-xs font-semibold"
              >
                {applications.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.job_title || 'Job'} ({a.stage})
                  </option>
                ))}
              </Select>
            </div>
            {canWrite && activeApp && (
              <Button size="sm" onClick={() => setScheduleOpen(true)}>
                <Plus size={14} />
                Schedule Interview
              </Button>
            )}
          </div>

          {/* Interviews & Scorecards */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Calendar size={16} className="text-brand-600" />
                <CardTitle className="text-sm">Interviews &amp; Scorecards ({interviews.length})</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {interviews.length === 0 ? (
                <p className="rounded-xl border border-dashed border-stone-200 py-6 text-center text-xs text-slate-500">
                  No interviews scheduled for this application yet.
                </p>
              ) : (
                interviews.map((iv) => (
                  <div
                    key={iv.id}
                    className="rounded-xl border border-stone-200/80 bg-stone-50/40 p-4 space-y-3"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-slate-900">{iv.round_name}</p>
                          <Badge variant="secondary" className="capitalize">{iv.status}</Badge>
                          <Badge variant="brand" className="capitalize">{iv.mode}</Badge>
                          {iv.scorecard_aggregate.count > 0 && (
                            <Badge variant="success">
                              ★ {iv.scorecard_aggregate.average_rating}/{iv.scorecard_aggregate.scale} (
                              {iv.scorecard_aggregate.count})
                            </Badge>
                          )}
                        </div>
                        <p className="mt-1 text-xs text-slate-600">
                          {formatIST(iv.scheduled_at)} · {iv.duration_minutes} mins
                          {iv.location_or_link ? ` · ${iv.location_or_link}` : ''}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-1.5">
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
                          .ics
                        </Button>
                        <Button
                          variant="soft"
                          size="sm"
                          onClick={() => void openScorecardPanel(iv.id)}
                        >
                          <Star size={13} />
                          Scorecards
                        </Button>
                      </div>
                    </div>

                    {activeScorecardIvId === iv.id && ivScorecards && (
                      <div className="rounded-xl border border-stone-200 bg-white p-4 space-y-3 animate-fade-in">
                        {ivScorecards.viewer_aggregate_only && (
                          <p className="text-xs text-slate-600">
                            Viewer access shows scorecard aggregates only ({ivScorecards.aggregate.count}{' '}
                            submitted, average {ivScorecards.aggregate.average_rating ?? '—'}/
                            {ivScorecards.aggregate.scale}).
                          </p>
                        )}

                        {ivScorecards.peer_scorecards_locked && (
                          <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                            <Lock size={14} className="shrink-0" />
                            Other interviewers&apos; scorecards are hidden until you submit yours.
                          </div>
                        )}

                        {ivScorecards.scorecards.length > 0 && (
                          <div className="space-y-2">
                            {ivScorecards.scorecards.map((sc) => (
                              <div
                                key={sc.id}
                                className="rounded-lg border border-stone-200/80 bg-stone-50/50 p-3 text-xs space-y-1"
                              >
                                <div className="flex items-center justify-between gap-2">
                                  <span className="font-semibold text-slate-900">
                                    {sc.interviewer_name || sc.interviewer_email}
                                  </span>
                                  <div className="flex items-center gap-1.5">
                                    {sc.average_rating != null && (
                                      <Badge variant="brand">★ {sc.average_rating}</Badge>
                                    )}
                                    <Badge variant="secondary" className="capitalize">
                                      {sc.recommendation.replace('_', ' ')}
                                    </Badge>
                                  </div>
                                </div>
                                {sc.comments && <p className="text-slate-600">{sc.comments}</p>}
                              </div>
                            ))}
                          </div>
                        )}

                        {canWrite && (
                          <div className="border-t border-stone-100 pt-3 space-y-3">
                            <p className="text-xs font-bold text-slate-800">
                              {ivScorecards.my_submitted ? 'Update Your Scorecard' : 'Submit Your Scorecard'}
                            </p>
                            {scorecardTemplates[0] && (
                              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                                {scorecardTemplates[0].competencies.map((comp) => (
                                  <div
                                    key={comp.name}
                                    className="flex items-center justify-between gap-2 rounded-lg border border-stone-200 px-3 py-1.5 text-xs"
                                  >
                                    <span className="font-medium text-slate-700">{comp.name}</span>
                                    <Select
                                      value={String(ratings[comp.name] ?? 4)}
                                      onChange={(e) =>
                                        setRatings((p) => ({
                                          ...p,
                                          [comp.name]: Number(e.target.value),
                                        }))
                                      }
                                      className="h-7 w-16 text-xs"
                                    >
                                      {[1, 2, 3, 4, 5].map((n) => (
                                        <option key={n} value={n}>
                                          {n}
                                        </option>
                                      ))}
                                    </Select>
                                  </div>
                                ))}
                              </div>
                            )}
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                              <Select
                                value={recommendation}
                                onChange={(e) =>
                                  setRecommendation(
                                    e.target.value as 'strong_no' | 'no' | 'yes' | 'strong_yes',
                                  )
                                }
                              >
                                <option value="strong_yes">Strong Yes</option>
                                <option value="yes">Yes</option>
                                <option value="no">No</option>
                                <option value="strong_no">Strong No</option>
                              </Select>
                              <Input
                                value={comments}
                                onChange={(e) => setComments(e.target.value)}
                                placeholder="Concise evidence-based interview notes…"
                                className="sm:col-span-2"
                              />
                            </div>
                            <Button
                              size="sm"
                              loading={submittingSc}
                              onClick={() => void handleSubmitScorecard(iv.id)}
                            >
                              <CheckCircle2 size={14} />
                              Submit Scorecard
                            </Button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))
              )}
            </CardContent>
          </Card>

          {/* Offers (admin/recruiter only) */}
          {canWrite && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Wallet size={16} className="text-brand-600" />
                    <CardTitle className="text-sm">Offers ({offers.length})</CardTitle>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowOfferForm((v) => !v)}
                  >
                    <Plus size={14} />
                    New Offer
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {showOfferForm && (
                  <form
                    onSubmit={handleCreateOffer}
                    className="rounded-xl border border-brand-200 bg-brand-50/30 p-4 space-y-3"
                  >
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                      <div className="space-y-1">
                        <Label htmlFor="off-ctc">Offered CTC *</Label>
                        <Input
                          id="off-ctc"
                          type="number"
                          required
                          min={1}
                          value={offerCtc}
                          onChange={(e) => setOfferCtc(e.target.value)}
                          placeholder="1800000"
                        />
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="off-cur">Currency</Label>
                        <Select
                          id="off-cur"
                          value={offerCurrency}
                          onChange={(e) => setOfferCurrency(e.target.value)}
                        >
                          <option value="INR">INR</option>
                          <option value="USD">USD</option>
                          <option value="EUR">EUR</option>
                          <option value="GBP">GBP</option>
                        </Select>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor="off-st">Status</Label>
                        <Select
                          id="off-st"
                          value={offerStatus}
                          onChange={(e) =>
                            setOfferStatus(
                              e.target.value as
                                | 'draft'
                                | 'extended'
                                | 'accepted'
                                | 'declined'
                                | 'withdrawn',
                            )
                          }
                        >
                          <option value="draft">Draft</option>
                          <option value="extended">Extended (moves to Offer)</option>
                          <option value="accepted">Accepted (moves to Hired)</option>
                        </Select>
                      </div>
                    </div>
                    <Textarea
                      rows={2}
                      value={offerNotes}
                      onChange={(e) => setOfferNotes(e.target.value)}
                      placeholder="Joining date defaults from candidate notice period if left blank…"
                    />
                    <div className="flex justify-end gap-2">
                      <Button type="button" variant="ghost" size="sm" onClick={() => setShowOfferForm(false)}>
                        Cancel
                      </Button>
                      <Button type="submit" size="sm" loading={savingOffer}>
                        Save Offer
                      </Button>
                    </div>
                  </form>
                )}

                {offers.length === 0 && !showOfferForm ? (
                  <p className="text-xs text-slate-500">No offers drafted for this application yet.</p>
                ) : (
                  offers.map((o) => (
                    <div
                      key={o.id}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-stone-200/80 bg-stone-50/40 p-3.5 text-xs"
                    >
                      <div>
                        <p className="font-bold text-slate-900">
                          {formatCtc(o.offered_ctc, o.currency)}{' '}
                          <Badge variant="brand" className="ml-1 capitalize">
                            {o.status}
                          </Badge>
                        </p>
                        <p className="mt-0.5 text-slate-500">
                          Expected joining: {o.expected_joining_date || 'TBD'}
                          {o.notes ? ` · ${o.notes}` : ''}
                        </p>
                      </div>
                      <Select
                        value={o.status}
                        onChange={(e) => void handleOfferStatus(o.id, e.target.value)}
                        className="h-8 w-36 text-xs capitalize"
                      >
                        <option value="draft">Draft</option>
                        <option value="extended">Extended</option>
                        <option value="accepted">Accepted</option>
                        <option value="declined">Declined</option>
                        <option value="withdrawn">Withdrawn</option>
                      </Select>
                    </div>
                  ))
                )}
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* Email Notification Composer (admin/recruiter) + Sent Log */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center gap-2">
            <Mail size={16} className="text-brand-600" />
            <CardTitle className="text-sm">Candidate Emails ({emailLogs.length})</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {canWrite && !blindMode && (
            <div className="space-y-3 rounded-xl border border-stone-200/80 bg-stone-50/40 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Select
                  value={selectedTplKey}
                  onChange={(e) => {
                    setSelectedTplKey(e.target.value)
                    setEmailPreview(null)
                  }}
                  className="h-9 w-64 text-xs"
                >
                  {emailTemplates.map((t) => (
                    <option key={t.id} value={t.key}>
                      {t.key}
                    </option>
                  ))}
                </Select>
                <Button variant="outline" size="sm" onClick={() => void handlePreviewEmail()}>
                  Preview Email
                </Button>
                {!candidateEmail && (
                  <span className="text-xs text-amber-700">No candidate email on file</span>
                )}
              </div>

              {emailPreview && (
                <div className="space-y-2.5 rounded-xl border border-brand-200 bg-white p-3.5 text-xs animate-fade-in">
                  <p className="text-slate-500">
                    To: <span className="font-semibold text-slate-900">{emailPreview.to || '—'}</span>
                  </p>
                  <Input
                    value={emailPreview.subject}
                    onChange={(e) =>
                      setEmailPreview((p) => (p ? { ...p, subject: e.target.value } : p))
                    }
                  />
                  <Textarea
                    rows={5}
                    value={emailPreview.body}
                    onChange={(e) =>
                      setEmailPreview((p) => (p ? { ...p, body: e.target.value } : p))
                    }
                  />
                  {selectedTplKey.toLowerCase().includes('reject') && (
                    <label className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-900">
                      <input
                        type="checkbox"
                        checked={confirmRejection}
                        onChange={(e) => setConfirmRejection(e.target.checked)}
                      />
                      I confirm sending this rejection email to {displayName}.
                    </label>
                  )}
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setEmailPreview(null)}>
                      Cancel
                    </Button>
                    <Button size="sm" loading={sendingEmail} onClick={() => void handleSendEmail()}>
                      <Send size={13} />
                      Send Email
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {emailLogs.length > 0 && (
            <ul className="space-y-2">
              {emailLogs.map((log) => (
                <li
                  key={log.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-stone-200/80 px-3.5 py-2.5 text-xs"
                >
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-slate-900">{log.subject}</p>
                    <p className="text-slate-500">
                      {log.template_key || 'custom'} · {formatRelativeDate(log.created_at)}
                    </p>
                  </div>
                  <Badge variant={log.status === 'sent' ? 'success' : 'warning'}>{log.status}</Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {activeApp && (
        <ScheduleInterviewModal
          open={scheduleOpen}
          applicationId={activeApp.id}
          candidateLabel={displayName}
          jobTitle={activeApp.job_title}
          onClose={() => setScheduleOpen(false)}
          onScheduled={() => {
            void loadAppDetails(activeApp.id)
            onActivityChange?.()
          }}
        />
      )}
    </div>
  )
}
