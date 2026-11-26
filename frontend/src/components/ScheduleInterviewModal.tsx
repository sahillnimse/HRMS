import { useEffect, useState } from 'react'
import { Calendar, Clock, Download, Video, X } from 'lucide-react'
import { api, downloadBlobFile, getErrorMessage } from '@/lib/api'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { useAddToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import type { InterviewItem, InterviewParticipant } from '@/types'

interface ScheduleInterviewModalProps {
  open: boolean
  applicationId: string
  candidateLabel: string
  jobTitle?: string | null
  onClose: () => void
  onScheduled?: (interview: InterviewItem) => void
}

function defaultLocalDateTime(): string {
  const d = new Date(Date.now() + 24 * 60 * 60 * 1000)
  d.setMinutes(0, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`
}

export function ScheduleInterviewModal({
  open,
  applicationId,
  candidateLabel,
  jobTitle,
  onClose,
  onScheduled,
}: ScheduleInterviewModalProps) {
  const addToast = useAddToast()
  const { blindMode } = useBlindMode()

  const [roundName, setRoundName] = useState('Technical Round 1')
  const [scheduledLocal, setScheduledLocal] = useState(defaultLocalDateTime)
  const [duration, setDuration] = useState('45')
  const [mode, setMode] = useState<'video' | 'phone' | 'onsite'>('video')
  const [locationOrLink, setLocationOrLink] = useState('')
  const [interviewers, setInterviewers] = useState<InterviewParticipant[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [created, setCreated] = useState<InterviewItem | null>(null)

  useEffect(() => {
    if (!open) return
    setCreated(null)
    api
      .get<InterviewParticipant[]>('/interviews/interviewers')
      .then((res) => setInterviewers(res.data))
      .catch(() => {})
  }, [open])

  if (!open) return null

  const toggleParticipant = (uid: string) => {
    setSelectedIds((prev) => (prev.includes(uid) ? prev.filter((x) => x !== uid) : [...prev, uid]))
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!roundName.trim() || !scheduledLocal) return
    setSaving(true)
    try {
      const isoUtc = new Date(scheduledLocal).toISOString()
      const res = await api.post<InterviewItem>(`/applications/${applicationId}/interviews`, {
        round_name: roundName.trim(),
        scheduled_at: isoUtc,
        duration_minutes: Number(duration) || 45,
        mode,
        location_or_link: locationOrLink.trim(),
        participant_ids: selectedIds,
      })
      setCreated(res.data)
      onScheduled?.(res.data)
      addToast('Interview scheduled', 'success')
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to schedule interview'), 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleDownloadIcs = async () => {
    if (!created) return
    try {
      await downloadBlobFile(
        `/interviews/${created.id}/ics`,
        { blind: blindMode },
        `interview-${created.id.slice(0, 8)}.ics`,
      )
      addToast('Calendar invite (.ics) downloaded', 'info')
    } catch {
      addToast('Failed to download .ics invite', 'error')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="absolute inset-0 bg-slate-900/35 backdrop-blur-sm"
        onClick={() => !saving && onClose()}
      />
      <div className="relative w-full max-w-lg rounded-2xl border border-stone-200 bg-white p-6 shadow-2xl animate-scale-in">
        <div className="flex items-start justify-between gap-3 border-b border-stone-100 pb-3.5">
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-brand-600">
              Schedule Interview
            </p>
            <h3 className="font-display text-base font-bold text-slate-900">
              {candidateLabel}
              {jobTitle ? ` · ${jobTitle}` : ''}
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-stone-100 hover:text-slate-700"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        {created ? (
          <div className="mt-5 space-y-4 text-center">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600">
              <Calendar size={22} />
            </div>
            <div>
              <p className="text-sm font-bold text-slate-900">{created.round_name} Scheduled</p>
              <p className="mt-1 text-xs text-slate-500">
                {new Intl.DateTimeFormat('en-IN', {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                  timeZone: 'Asia/Kolkata',
                }).format(new Date(created.scheduled_at))}{' '}
                IST ({created.duration_minutes} mins · {created.mode})
              </p>
            </div>
            <div className="flex justify-center gap-2 pt-2">
              <Button variant="outline" size="sm" onClick={() => void handleDownloadIcs()}>
                <Download size={14} />
                Download .ics Invite
              </Button>
              <Button size="sm" onClick={onClose}>
                Done
              </Button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="mt-4 space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="iv-round">Round Name *</Label>
              <Input
                id="iv-round"
                required
                value={roundName}
                onChange={(e) => setRoundName(e.target.value)}
                placeholder="Technical Round 1 / Hiring Manager"
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="iv-when" className="inline-flex items-center gap-1">
                  <Clock size={12} /> Date &amp; Time (IST / local)
                </Label>
                <Input
                  id="iv-when"
                  type="datetime-local"
                  required
                  value={scheduledLocal}
                  onChange={(e) => setScheduledLocal(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="iv-dur">Duration</Label>
                <Select id="iv-dur" value={duration} onChange={(e) => setDuration(e.target.value)}>
                  <option value="30">30 minutes</option>
                  <option value="45">45 minutes</option>
                  <option value="60">60 minutes</option>
                  <option value="90">90 minutes</option>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="iv-mode" className="inline-flex items-center gap-1">
                  <Video size={12} /> Mode
                </Label>
                <Select
                  id="iv-mode"
                  value={mode}
                  onChange={(e) => setMode(e.target.value as 'video' | 'phone' | 'onsite')}
                >
                  <option value="video">Video Call</option>
                  <option value="phone">Phone Screen</option>
                  <option value="onsite">Onsite</option>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="iv-loc">Meeting Link / Room</Label>
                <Input
                  id="iv-loc"
                  value={locationOrLink}
                  onChange={(e) => setLocationOrLink(e.target.value)}
                  placeholder="https://meet.google.com/..."
                />
              </div>
            </div>

            {interviewers.length > 0 && (
              <div className="space-y-1.5">
                <Label>Interviewers (optional; defaults to you)</Label>
                <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto rounded-xl border border-stone-200 bg-stone-50/50 p-2">
                  {interviewers.map((u) => {
                    const active = selectedIds.includes(u.user_id)
                    return (
                      <button
                        key={u.user_id}
                        type="button"
                        onClick={() => toggleParticipant(u.user_id)}
                        className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                          active
                            ? 'border-brand-600 bg-brand-600 text-white'
                            : 'border-stone-200 bg-white text-slate-700 hover:border-brand-300'
                        }`}
                      >
                        {u.full_name}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 border-t border-stone-100 pt-3">
              <Button type="button" variant="outline" onClick={onClose} disabled={saving}>
                Skip for now
              </Button>
              <Button type="submit" loading={saving}>
                Schedule Interview
              </Button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
