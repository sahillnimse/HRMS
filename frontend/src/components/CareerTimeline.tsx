import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle,
  Briefcase,
  Calendar,
  Clock,
  GitMerge,
  HelpCircle,
  Info,
  Layers,
} from 'lucide-react'
import { api, getErrorMessage } from '@/lib/api'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Select } from '@/components/ui/Select'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import type { CandidateTimeline } from '@/types'

interface CareerTimelineProps {
  candidateId: string
}

function formatMonths(months: number | null): string {
  if (months == null) return 'Dates unclear'
  if (months < 12) return `${months} mo${months === 1 ? '' : 's'}`
  const yrs = Math.floor(months / 12)
  const rem = months % 12
  return rem === 0 ? `${yrs} yr${yrs === 1 ? '' : 's'}` : `${yrs}y ${rem}m`
}

export function CareerTimeline({ candidateId }: CareerTimelineProps) {
  const [gapMonths, setGapMonths] = useState(3)
  const [timeline, setTimeline] = useState<CandidateTimeline | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadTimeline = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<CandidateTimeline>(`/candidates/${candidateId}/timeline`, {
        params: { gap_months: gapMonths },
      })
      setTimeline(res.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load career timeline'))
    } finally {
      setLoading(false)
    }
  }, [candidateId, gapMonths])

  useEffect(() => {
    void loadTimeline()
  }, [loadTimeline])

  // Compute min/max month bounds for proportional timeline bars
  const bounds = useMemo(() => {
    if (!timeline) return null
    const valid = timeline.roles.filter(
      (r) => !r.has_invalid_dates && r.start_month_index != null && r.end_month_index != null,
    )
    if (valid.length === 0) return null
    const minM = Math.min(...valid.map((r) => r.start_month_index as number))
    const maxM = Math.max(...valid.map((r) => (r.end_month_index as number) + 1))
    const span = Math.max(1, maxM - minM)
    return { minM, maxM, span }
  }, [timeline])

  if (loading && !timeline) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="skeleton h-24 rounded-2xl" />
          ))}
        </div>
        <div className="skeleton h-72 rounded-2xl" />
      </div>
    )
  }

  if (error || !timeline) {
    return (
      <Card>
        <CardContent className="p-8 text-center space-y-3">
          <AlertCircle size={22} className="mx-auto text-coral-500" />
          <p className="text-sm text-slate-600">{error || 'Timeline unavailable.'}</p>
          <Button variant="outline" size="sm" onClick={() => void loadTimeline()}>
            Retry
          </Button>
        </CardContent>
      </Card>
    )
  }

  const { tenure_stats: stats, roles, gaps, overlaps, consistency_checks: checks } = timeline

  return (
    <div className="space-y-5 animate-fade-in">
      {/* Tenure Stat Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          {
            label: 'Computed Experience',
            value: `${stats.total_years.toFixed(1)} yrs`,
            sub: `${stats.dated_role_count} dated role${stats.dated_role_count === 1 ? '' : 's'}`,
            icon: Briefcase,
            tint: 'bg-brand-50 text-brand-600',
          },
          {
            label: 'Average Tenure',
            value: stats.dated_role_count > 0 ? formatMonths(Math.round(stats.average_tenure_months)) : '—',
            sub: `Across ${stats.role_count} total role${stats.role_count === 1 ? '' : 's'}`,
            icon: Clock,
            tint: 'bg-sky-50 text-sky-600',
          },
          {
            label: 'Jobs (Last 5 Years)',
            value: String(stats.jobs_last_5_years),
            sub: stats.short_stints_count > 0 ? `${stats.short_stints_count} short stint(s)` : 'Steady progression',
            icon: Calendar,
            tint: 'bg-amber-50 text-amber-600',
          },
          {
            label: 'Timeline Signals',
            value: `${gaps.length} gap${gaps.length === 1 ? '' : 's'} · ${overlaps.length} overlap${overlaps.length === 1 ? '' : 's'}`,
            sub: `Gap threshold > ${timeline.gap_threshold_months} mos`,
            icon: GitMerge,
            tint: 'bg-coral-50 text-coral-600',
          },
        ].map((item) => {
          const Icon = item.icon
          return (
            <div
              key={item.label}
              className="rounded-2xl border border-stone-200/80 bg-white p-4 shadow-card"
            >
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                  {item.label}
                </span>
                <span className={cn('flex h-8 w-8 items-center justify-center rounded-lg', item.tint)}>
                  <Icon size={15} />
                </span>
              </div>
              <p className="mt-2 font-display text-lg font-bold text-slate-900">{item.value}</p>
              <p className="mt-0.5 text-xs text-slate-500">{item.sub}</p>
            </div>
          )
        })}
      </div>

      {/* Visual Proportional Timeline */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Layers size={16} className="text-brand-600" />
              <CardTitle>Career Timeline</CardTitle>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <label htmlFor="gap-threshold">Gap marker:</label>
              <Select
                id="gap-threshold"
                value={String(gapMonths)}
                onChange={(e) => setGapMonths(Number(e.target.value))}
                className="h-8 w-28 text-xs"
              >
                <option value="2">&gt; 2 months</option>
                <option value="3">&gt; 3 months</option>
                <option value="6">&gt; 6 months</option>
                <option value="12">&gt; 12 months</option>
              </Select>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {roles.length === 0 ? (
            <p className="rounded-xl border border-dashed border-stone-200 py-8 text-center text-sm text-slate-500">
              No work history recorded for this candidate yet.
            </p>
          ) : (
            <div className="space-y-3">
              {roles.map((r) => {
                const leftPct =
                  bounds && !r.has_invalid_dates && r.start_month_index != null
                    ? ((r.start_month_index - bounds.minM) / bounds.span) * 100
                    : 0
                const widthPct =
                  bounds &&
                  !r.has_invalid_dates &&
                  r.start_month_index != null &&
                  r.end_month_index != null
                    ? Math.max(
                        4,
                        (((r.end_month_index + 1) - r.start_month_index) / bounds.span) * 100,
                      )
                    : 0

                return (
                  <div
                    key={`${r.index}-${r.company}-${r.job_title}`}
                    className="rounded-xl border border-stone-200/80 bg-stone-50/40 p-3.5 space-y-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-slate-900">
                          {r.job_title}{' '}
                          <span className="font-normal text-slate-500">at {r.company}</span>
                        </p>
                        <p className="text-xs text-slate-500">
                          {r.start_ym || r.raw_start || 'Unknown'} — {r.end_ym || r.raw_end || 'Unknown'}
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        {r.is_current && <Badge variant="success">Current</Badge>}
                        {r.has_invalid_dates && <Badge variant="warning">Check dates</Badge>}
                        <Badge variant="secondary">{formatMonths(r.duration_months)}</Badge>
                      </div>
                    </div>

                    {bounds && widthPct > 0 && (
                      <div className="relative h-2.5 w-full overflow-hidden rounded-full bg-stone-200/70">
                        <div
                          className={cn(
                            'absolute top-0 h-full rounded-full animate-bar-grow',
                            r.is_current
                              ? 'bg-gradient-to-r from-brand-500 to-teal-400'
                              : 'bg-gradient-to-r from-sky-500 to-brand-400',
                          )}
                          style={{
                            left: `${Math.min(96, Math.max(0, leftPct))}%`,
                            width: `${Math.min(100 - leftPct, widthPct)}%`,
                          }}
                        />
                      </div>
                    )}
                  </div>
                )
              })}

              {/* Gap & Overlap Markers */}
              {(gaps.length > 0 || overlaps.length > 0) && (
                <div className="grid grid-cols-1 gap-3 pt-2 md:grid-cols-2">
                  {gaps.length > 0 && (
                    <div className="rounded-xl border border-dashed border-amber-300 bg-amber-50/50 p-3.5 space-y-2">
                      <p className="text-xs font-bold uppercase tracking-wider text-amber-800">
                        Employment Gaps (&gt; {timeline.gap_threshold_months}m)
                      </p>
                      {gaps.map((g, idx) => (
                        <div key={`gap-${idx}`} className="text-xs text-amber-950">
                          <span className="font-semibold">
                            {g.from_ym} → {g.to_ym} ({formatMonths(g.duration_months)})
                          </span>
                          {g.between_roles.length === 2 && (
                            <p className="text-[11px] text-amber-800">
                              Between {g.between_roles[0]} &amp; {g.between_roles[1]}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {overlaps.length > 0 && (
                    <div className="rounded-xl border border-dashed border-sky-300 bg-sky-50/50 p-3.5 space-y-2">
                      <p className="text-xs font-bold uppercase tracking-wider text-sky-800">
                        Overlapping Dates
                      </p>
                      {overlaps.map((o, idx) => (
                        <div key={`ov-${idx}`} className="text-xs text-sky-950">
                          <span className="font-semibold">
                            {o.from_ym} → {o.to_ym} ({formatMonths(o.overlap_months)})
                          </span>
                          <p className="text-[11px] text-sky-800">{o.roles.join(' & ')}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Neutral Consistency Checks */}
      {checks.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-sm">Consistency Checks ({checks.length})</CardTitle>
              <span className="text-xs text-slate-400">
                Informational prompts for human review · never alters match scores
              </span>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {checks.map((c, idx) => (
              <div
                key={`${c.code}-${idx}`}
                className="flex items-start gap-2.5 rounded-xl border border-stone-200/80 bg-stone-50/50 px-3.5 py-2.5 text-xs text-slate-700"
              >
                {c.severity === 'check' ? (
                  <HelpCircle size={15} className="mt-0.5 shrink-0 text-amber-600" />
                ) : (
                  <Info size={15} className="mt-0.5 shrink-0 text-sky-600" />
                )}
                <p className="flex-1 leading-5">{c.message}</p>
                <Badge
                  variant={c.severity === 'check' ? 'warning' : 'secondary'}
                  className="shrink-0 text-[10px] uppercase"
                >
                  {c.severity}
                </Badge>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
