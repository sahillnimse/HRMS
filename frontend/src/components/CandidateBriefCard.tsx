import { useCallback, useEffect, useState } from 'react'
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  HelpCircle,
  Info,
  RefreshCw,
  Sparkles,
} from 'lucide-react'
import { api, getErrorMessage } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { useAddToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { cn, formatRelativeDate } from '@/lib/utils'
import type { CandidateBrief } from '@/types'

interface CandidateBriefCardProps {
  candidateId: string
  refreshKey?: number
}

export function CandidateBriefCard({ candidateId, refreshKey = 0 }: CandidateBriefCardProps) {
  const { canWrite } = useAuth()
  const { blindMode } = useBlindMode()
  const addToast = useAddToast()

  const [brief, setBrief] = useState<CandidateBrief | null>(null)
  const [loading, setLoading] = useState(true)
  const [regenerating, setRegenerating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showVerify, setShowVerify] = useState(false)

  const loadBrief = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<CandidateBrief>(`/candidates/${candidateId}/brief`, {
        params: blindMode ? { blind: true } : undefined,
      })
      setBrief(res.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Could not load candidate brief'))
    } finally {
      setLoading(false)
    }
  }, [candidateId, blindMode])

  useEffect(() => {
    void loadBrief()
  }, [loadBrief, refreshKey])

  const handleRegenerate = async () => {
    setRegenerating(true)
    try {
      const res = await api.post<CandidateBrief>(`/candidates/${candidateId}/brief/regenerate`, null, {
        params: blindMode ? { blind: true } : undefined,
      })
      setBrief(res.data)
      addToast('Candidate brief refreshed', 'success')
    } catch (err) {
      addToast(getErrorMessage(err, 'Failed to regenerate brief'), 'error')
    } finally {
      setRegenerating(false)
    }
  }

  if (loading && !brief) {
    return (
      <div className="rounded-2xl border border-brand-200/70 bg-white p-5 shadow-card space-y-3">
        <div className="skeleton h-4 w-36" />
        <div className="skeleton h-14 w-full" />
        <div className="flex gap-2">
          <div className="skeleton h-6 w-40 rounded-full" />
          <div className="skeleton h-6 w-44 rounded-full" />
        </div>
      </div>
    )
  }

  if (error || !brief) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-stone-200 bg-white px-5 py-3.5 text-xs text-slate-600 shadow-card">
        <span>{error || 'Brief unavailable right now.'}</span>
        <Button variant="outline" size="sm" onClick={() => void loadBrief()}>
          Retry
        </Button>
      </div>
    )
  }

  const verifyItems = brief.verify_items ?? []
  const checkCount = verifyItems.filter((v) => v.severity === 'check').length

  return (
    <section
      aria-label="Candidate Brief"
      className="overflow-hidden rounded-2xl border border-brand-200/80 bg-white shadow-card animate-fade-in"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-stone-100 bg-gradient-to-r from-brand-50/80 via-white to-coral-50/40 px-5 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white shadow-sm">
            <Sparkles size={14} />
          </span>
          <h2 className="font-display text-sm font-bold text-slate-900">Candidate Brief</h2>
          <Badge variant="secondary" className="text-[10px]">
            {brief.model === 'deterministic' ? 'Structured summary' : brief.model}
          </Badge>
          <span className="text-[11px] text-slate-400">
            Updated {formatRelativeDate(brief.generated_at)}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {verifyItems.length > 0 && (
            <button
              type="button"
              onClick={() => setShowVerify((v) => !v)}
              aria-expanded={showVerify}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-300',
                checkCount > 0
                  ? 'border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100'
                  : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100',
              )}
            >
              <HelpCircle size={13} />
              Worth verifying ({verifyItems.length})
              {showVerify ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
          )}
          {canWrite && (
            <Button
              variant="ghost"
              size="sm"
              loading={regenerating}
              onClick={() => void handleRegenerate()}
              title="Regenerate brief"
              className="h-8 px-2.5 text-xs"
            >
              <RefreshCw size={13} />
              Refresh
            </Button>
          )}
        </div>
      </div>

      <div className="p-5 space-y-4">
        {/* <= 5-line crisp summary */}
        <p className="whitespace-pre-line text-sm leading-6 text-slate-700 line-clamp-5">
          {brief.summary}
        </p>

        {/* 2-4 strengths */}
        {brief.strengths.length > 0 && (
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {brief.strengths.slice(0, 4).map((strength, idx) => (
              <div
                key={`str-${idx}`}
                className="flex items-start gap-2 rounded-xl border border-brand-100/80 bg-brand-50/40 px-3 py-2 text-xs text-slate-700"
              >
                <CheckCircle2 size={14} className="mt-0.5 shrink-0 text-brand-600" />
                <span className="leading-5">{strength}</span>
              </div>
            ))}
          </div>
        )}

        {/* Progressive disclosure: 0-4 neutral "Worth verifying" items */}
        {showVerify && verifyItems.length > 0 && (
          <div className="rounded-xl border border-amber-200/80 bg-amber-50/50 p-4 space-y-2.5 animate-fade-in">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-xs font-bold text-amber-950">Worth Verifying in Conversation</p>
              <span className="text-[11px] text-amber-800/90">
                Informational only · does not affect match scores
              </span>
            </div>
            <ul className="space-y-2">
              {verifyItems.map((item, idx) => (
                <li
                  key={`${item.code}-${idx}`}
                  className="flex items-start gap-2.5 rounded-lg border border-amber-200/60 bg-white/90 px-3 py-2 text-xs text-slate-700"
                >
                  {item.severity === 'check' ? (
                    <HelpCircle size={14} className="mt-0.5 shrink-0 text-amber-600" />
                  ) : (
                    <Info size={14} className="mt-0.5 shrink-0 text-sky-600" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="leading-5">{item.message}</p>
                  </div>
                  <Badge
                    variant={item.severity === 'check' ? 'warning' : 'secondary'}
                    className="shrink-0 text-[10px] uppercase"
                  >
                    {item.severity}
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  )
}
