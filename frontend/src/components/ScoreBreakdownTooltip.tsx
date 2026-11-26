import { useState, useRef, useEffect } from 'react'
import { Check, Info, Sparkles, X } from 'lucide-react'
import type { JobMatchBreakdown } from '@/types'
import { cn } from '@/lib/utils'

interface ScoreBreakdownTooltipProps {
  score: number
  breakdown: JobMatchBreakdown
  align?: 'left' | 'right'
}

function getScoreTone(score: number) {
  if (score >= 75) {
    return {
      pill: 'border-emerald-200 bg-emerald-50 text-emerald-800 hover:border-emerald-300',
      bar: 'bg-emerald-500',
      label: 'Strong match',
    }
  }
  if (score >= 50) {
    return {
      pill: 'border-amber-200 bg-amber-50 text-amber-800 hover:border-amber-300',
      bar: 'bg-amber-500',
      label: 'Moderate match',
    }
  }
  return {
    pill: 'border-rose-200 bg-rose-50 text-rose-800 hover:border-rose-300',
    bar: 'bg-rose-500',
    label: 'Partial match',
  }
}

export function ScoreBreakdownTooltip({
  score,
  breakdown,
  align = 'left',
}: ScoreBreakdownTooltipProps) {
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const tone = getScoreTone(score)

  useEffect(() => {
    if (!open) return
    const onDocClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [open])

  const weights = breakdown?.weights ?? {
    must_have: 0.45,
    experience_fit: 0.25,
    nice_to_have: 0.15,
    semantic: 0.15,
  }

  const rows = [
    {
      label: 'Must-have skills',
      weight: Math.round((weights.must_have ?? 0.45) * 100),
      value: breakdown?.must_have_score ?? 0,
      barClass: 'bg-brand-500',
    },
    {
      label: 'Experience fit',
      weight: Math.round((weights.experience_fit ?? 0.25) * 100),
      value: breakdown?.experience_score ?? 0,
      barClass: 'bg-sky-500',
    },
    {
      label: 'Nice-to-have skills',
      weight: Math.round((weights.nice_to_have ?? 0.15) * 100),
      value: breakdown?.nice_to_have_score ?? 0,
      barClass: 'bg-emerald-500',
    },
    {
      label:
        breakdown?.semantic_mode === 'embedding'
          ? 'Semantic similarity'
          : 'Contextual overlap',
      weight: Math.round((weights.semantic ?? 0.15) * 100),
      value: breakdown?.semantic_score ?? 0,
      barClass: 'bg-violet-500',
    },
  ]

  const matchedReq = breakdown?.matched_required_skills ?? []
  const missingReq = breakdown?.missing_required_skills ?? []
  const adjacentSkills = breakdown?.adjacent_skills ?? []
  const matchedNice = breakdown?.matched_nice_skills ?? []
  const whyText = breakdown?.why

  return (
    <div
      ref={containerRef}
      className="relative inline-block"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold transition focus:outline-none focus:ring-2 focus:ring-brand-500/30',
          tone.pill,
        )}
        title="View score breakdown"
      >
        <span className="tabular-nums">{Math.round(score)}/100</span>
        <Info size={12} className="opacity-70" />
      </button>

      {open && (
        <div
          className={cn(
            'absolute top-full z-40 mt-2 w-80 rounded-2xl border border-slate-200 bg-white p-4 shadow-xl animate-fade-in',
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
            <div>
              <p className="text-xs font-bold text-slate-900">Deterministic Match Score</p>
              <p className="text-[11px] text-slate-500">{tone.label}</p>
            </div>
            <span className={cn('rounded-lg border px-2 py-0.5 text-sm font-bold tabular-nums', tone.pill)}>
              {score.toFixed(1)}
            </span>
          </div>

          {whyText && (
            <p className="mt-2.5 rounded-lg bg-brand-50/70 px-2.5 py-2 text-[11px] leading-4 text-slate-700">
              {whyText}
            </p>
          )}

          <div className="mt-3 space-y-2.5">
            {rows.map((r) => (
              <div key={r.label}>
                <div className="mb-1 flex items-center justify-between text-[11px]">
                  <span className="font-medium text-slate-700">
                    {r.label} <span className="text-slate-400">({r.weight}%)</span>
                  </span>
                  <span className="font-semibold tabular-nums text-slate-800">
                    {Math.round(r.value)}%
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={cn('h-full rounded-full transition-all', r.barClass)}
                    style={{ width: `${Math.max(4, Math.min(100, r.value))}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {(matchedReq.length > 0 || missingReq.length > 0) && (
            <div className="mt-3.5 border-t border-slate-100 pt-3 space-y-2">
              {matchedReq.length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                    Matched Required ({matchedReq.length})
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {matchedReq.map((sk) => (
                      <span
                        key={`mr-${sk}`}
                        className="inline-flex items-center gap-0.5 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-800"
                      >
                        <Check size={10} />
                        {sk}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {missingReq.length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-rose-700">
                    Missing Required ({missingReq.length})
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {missingReq.map((sk) => (
                      <span
                        key={`mis-${sk}`}
                        className="inline-flex items-center gap-0.5 rounded bg-rose-50 px-1.5 py-0.5 text-[10px] font-medium text-rose-800"
                      >
                        <X size={10} />
                        {sk}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {adjacentSkills.length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-sky-700">
                    Adjacent / Transferable ({adjacentSkills.length})
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {adjacentSkills.slice(0, 4).map((adj, idx) => (
                      <span
                        key={`adj-${idx}-${adj.required_skill}`}
                        title={adj.relation}
                        className="rounded bg-sky-50 px-1.5 py-0.5 text-[10px] font-medium text-sky-800"
                      >
                        {adj.candidate_skill} → {adj.required_skill}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {matchedNice.length > 0 && (
                <div>
                  <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-brand-700">
                    Bonus Skills ({matchedNice.length})
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {matchedNice.map((sk) => (
                      <span
                        key={`mn-${sk}`}
                        className="rounded bg-brand-50 px-1.5 py-0.5 text-[10px] font-medium text-brand-800"
                      >
                        {sk}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="mt-3 flex items-center justify-between border-t border-slate-100 pt-2 text-[10px] text-slate-400">
            <span>
              Exp: {breakdown?.candidate_years ?? 0} yrs
              {breakdown?.job_min_years != null || breakdown?.job_max_years != null
                ? ` (target ${breakdown?.job_min_years ?? 0}–${breakdown?.job_max_years ?? '15+'})`
                : ''}
            </span>
            <span className="inline-flex items-center gap-1 font-medium text-slate-500">
              <Sparkles size={10} />
              {breakdown?.semantic_mode === 'embedding' ? 'Vector' : 'Lexical'}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
