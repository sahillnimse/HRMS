import { useEffect, useState } from 'react'
import { Check, Copy, HelpCircle, Sparkles, X } from 'lucide-react'
import { api, getErrorMessage } from '@/lib/api'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { useAddToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Select } from '@/components/ui/Select'
import type { InterviewQuestionsResponse, JobItem } from '@/types'

interface InterviewQuestionsModalProps {
  open: boolean
  candidateId: string
  candidateLabel: string
  onClose: () => void
}

const CATEGORY_LABELS: Record<string, string> = {
  skill_gap: 'Skill Gap',
  project_deep_dive: 'Project Deep Dive',
  technical: 'Technical',
  verification: 'Worth Verifying',
  behavioral: 'Collaboration',
}

const CATEGORY_VARIANT: Record<string, 'brand' | 'warning' | 'secondary' | 'outline' | 'success'> = {
  skill_gap: 'warning',
  project_deep_dive: 'brand',
  technical: 'secondary',
  verification: 'outline',
  behavioral: 'success',
}

export function InterviewQuestionsModal({
  open,
  candidateId,
  candidateLabel,
  onClose,
}: InterviewQuestionsModalProps) {
  const { blindMode } = useBlindMode()
  const addToast = useAddToast()

  const [jobs, setJobs] = useState<JobItem[]>([])
  const [jobId, setJobId] = useState('')
  const [data, setData] = useState<InterviewQuestionsResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (!open) return
    api
      .get<JobItem[]>('/jobs')
      .then((res) => setJobs(res.data || []))
      .catch(() => {})
  }, [open])

  const generate = async (selectedJobId = jobId) => {
    setLoading(true)
    try {
      const res = await api.post<InterviewQuestionsResponse>(
        `/candidates/${candidateId}/interview-questions`,
        {
          job_id: selectedJobId || null,
          count: 6,
          blind: blindMode,
        },
      )
      setData(res.data)
    } catch (err) {
      addToast(getErrorMessage(err, 'Could not generate interview questions'), 'error')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (open && !data) {
      void generate('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  if (!open) return null

  const copyAll = async () => {
    if (!data?.questions.length) return
    const text = data.questions
      .map(
        (q, idx) =>
          `${idx + 1}. [${CATEGORY_LABELS[q.category] || q.category} — ${q.target_topic}]\n` +
          `Q: ${q.question}\nLook for: ${q.what_to_look_for}`,
      )
      .join('\n\n')
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      addToast('Questions copied to clipboard', 'success')
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      addToast('Could not access clipboard', 'error')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-slate-900/35 backdrop-blur-sm" onClick={onClose} />
      <div className="relative flex max-h-[88vh] w-full max-w-2xl flex-col rounded-2xl border bg-white p-6 shadow-2xl animate-fade-in">
        <div className="flex items-start justify-between gap-3 border-b border-stone-100 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white">
                <Sparkles size={14} />
              </span>
              <h3 className="font-display text-base font-bold text-slate-900">
                Interview Question Guide
              </h3>
              {data && (
                <Badge variant="secondary" className="text-[10px]">
                  {data.model === 'deterministic' ? 'Structured guide' : data.model}
                </Badge>
              )}
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Tailored for <strong>{candidateLabel}</strong> from projects, skills, JD gaps &amp;
              neutral verification prompts.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-stone-100 hover:text-slate-700"
          >
            <X size={18} />
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Select
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            className="h-9 flex-1 min-w-[200px] text-xs"
          >
            <option value="">General technical screen (no specific job)</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                Tailor to Job: {j.title}
              </option>
            ))}
          </Select>
          <Button size="sm" onClick={() => void generate(jobId)} loading={loading}>
            <Sparkles size={13} />
            Regenerate
          </Button>
          {data && data.questions.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => void copyAll()}>
              {copied ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
              {copied ? 'Copied' : 'Copy All'}
            </Button>
          )}
        </div>

        <div className="mt-4 flex-1 space-y-3 overflow-y-auto pr-1">
          {loading ? (
            <div className="space-y-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="skeleton h-24 rounded-xl" />
              ))}
            </div>
          ) : !data || data.questions.length === 0 ? (
            <div className="py-10 text-center text-sm text-slate-500">
              <HelpCircle size={22} className="mx-auto mb-2 text-slate-300" />
              Click Regenerate to build tailored questions.
            </div>
          ) : (
            data.questions.map((q, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-stone-200/80 bg-stone-50/40 p-4 space-y-2"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-brand-100 text-[11px] font-bold text-brand-800">
                      {idx + 1}
                    </span>
                    <Badge variant={CATEGORY_VARIANT[q.category] || 'secondary'} className="text-[10px]">
                      {CATEGORY_LABELS[q.category] || q.category}
                    </Badge>
                    <span className="text-xs font-semibold text-slate-700">{q.target_topic}</span>
                  </div>
                </div>
                <p className="text-sm font-medium leading-6 text-slate-900">{q.question}</p>
                <p className="rounded-lg bg-white/80 px-3 py-2 text-xs leading-5 text-slate-600 border border-stone-200/60">
                  <strong className="text-slate-800">What to look for:</strong> {q.what_to_look_for}
                </p>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
