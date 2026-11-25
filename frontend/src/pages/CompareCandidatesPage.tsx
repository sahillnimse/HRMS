import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowUpRight,
  Award,
  Briefcase,
  Check,
  Clock,
  EyeOff,
  GraduationCap,
  MapPin,
  Sparkles,
  Wallet,
} from 'lucide-react'
import { api, getErrorMessage } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { computeCompleteness, formatCtc, getSeniority } from '@/lib/profile'
import { cn, formatYears } from '@/lib/utils'
import { PageHeader } from '@/components/layout/PageHeader'
import { ScoreBreakdownTooltip } from '@/components/ScoreBreakdownTooltip'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import type { CandidateCompareResponse } from '@/types'

export default function CompareCandidatesPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const { blindMode } = useBlindMode()

  const idsParam = searchParams.get('ids') || ''
  const jobIdParam = searchParams.get('jobId') || searchParams.get('job_id') || ''

  const [data, setData] = useState<CandidateCompareResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const cleanIds = idsParam
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    if (cleanIds.length < 2 || cleanIds.length > 3) {
      setError('Select between 2 and 3 candidates to compare side-by-side.')
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    api
      .get<CandidateCompareResponse>('/candidates/compare', {
        params: {
          ids: cleanIds.join(','),
          job_id: jobIdParam || undefined,
          blind: blindMode || undefined,
        },
      })
      .then((res) => {
        if (!cancelled) setData(res.data)
      })
      .catch((err) => {
        if (!cancelled) setError(getErrorMessage(err, 'Could not load comparison'))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [idsParam, jobIdParam, blindMode])

  const sharedSet = useMemo(
    () => new Set((data?.shared_skills ?? []).map((s) => s.toLowerCase())),
    [data],
  )

  const colGridClass =
    (data?.candidates.length ?? 2) === 3
      ? 'grid-cols-1 lg:grid-cols-3'
      : 'grid-cols-1 lg:grid-cols-2'

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="skeleton h-12 w-72" />
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="skeleton h-96 rounded-2xl" />
          <div className="skeleton h-96 rounded-2xl" />
        </div>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="mx-auto max-w-lg rounded-2xl border bg-white p-10 text-center shadow-card">
        <AlertTriangle size={24} className="mx-auto mb-3 text-amber-500" />
        <h2 className="text-lg font-semibold text-slate-900">Unable to compare candidates</h2>
        <p className="mt-1 text-sm text-slate-500">{error || 'Missing comparison data.'}</p>
        <div className="mt-5 flex justify-center gap-2">
          <Button variant="outline" onClick={() => navigate('/candidates')}>
            Go to Candidates
          </Button>
          {jobIdParam && (
            <Button onClick={() => navigate(`/jobs/${jobIdParam}`)}>Back to Job</Button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        onBack={() => (jobIdParam ? navigate(`/jobs/${jobIdParam}`) : navigate('/candidates'))}
        backLabel={jobIdParam ? 'Back to Job' : 'Candidates'}
        eyebrow="Side-by-Side Comparison"
        title={`Comparing ${data.candidates.length} Candidates`}
        description="Evaluate skills overlap, career trajectory, education, and job fit side-by-side."
      />

      {/* Shared Skills Banner */}
      <div className="rounded-2xl border border-emerald-200/80 bg-emerald-50/60 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-900">
            <Check size={14} className="text-emerald-600" />
            Shared Skills Across All {data.candidates.length} Candidates ({data.shared_skills.length}
            ):
          </span>
          {data.shared_skills.length > 0 ? (
            data.shared_skills.map((sk) => (
              <span
                key={`shared-${sk}`}
                className="rounded-md border border-emerald-200 bg-white px-2 py-0.5 text-xs font-medium text-emerald-800"
              >
                {sk}
              </span>
            ))
          ) : (
            <span className="text-xs text-emerald-800/80">
              No overlapping normalized skills across every selected candidate.
            </span>
          )}
        </div>
      </div>

      {/* Candidate Comparison Columns */}
      <div className={cn('grid gap-5', colGridClass)}>
        {data.candidates.map((c) => {
          const completeness = computeCompleteness(c)
          const match = data.job_matches?.[c.id]
          const latestRole = c.work_experience?.[0]

          return (
            <div
              key={c.id}
              className="flex flex-col rounded-2xl border border-slate-200/80 bg-white shadow-card overflow-hidden"
            >
              {/* Header */}
              <div className="border-b border-slate-100 bg-slate-50/60 p-5 space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    {blindMode ? (
                      <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
                        <EyeOff size={18} />
                      </div>
                    ) : (
                      <Avatar name={c.full_name} size="md" />
                    )}
                    <div className="min-w-0">
                      <Link
                        to={`/candidates/${c.id}`}
                        className="truncate text-base font-bold text-slate-900 hover:text-brand-600 block"
                      >
                        {c.full_name}
                      </Link>
                      <p className="truncate text-xs text-slate-500">
                        {latestRole
                          ? `${latestRole.job_title} · ${latestRole.company}`
                          : c.email || '—'}
                      </p>
                    </div>
                  </div>
                  <Link
                    to={`/candidates/${c.id}`}
                    className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-slate-200 bg-white text-slate-500 hover:border-brand-300 hover:text-brand-600"
                    title="Open full profile"
                  >
                    <ArrowUpRight size={15} />
                  </Link>
                </div>

                <div className="flex flex-wrap items-center gap-1.5">
                  <Badge variant="brand">{c.primary_domain}</Badge>
                  <Badge variant="secondary">
                    <Briefcase size={11} />
                    {formatYears(c.years_experience)} · {getSeniority(c.years_experience)}
                  </Badge>
                  <Badge variant="secondary">{completeness.score}% complete</Badge>
                </div>

                {c.city && (
                  <p className="inline-flex items-center gap-1 text-xs text-slate-500">
                    <MapPin size={12} className="text-slate-400" />
                    {c.city}
                  </p>
                )}

                {match && (
                  <div className="rounded-xl border border-brand-100 bg-white p-3 space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1 text-xs font-semibold text-slate-700">
                        <Sparkles size={12} className="text-brand-600" />
                        Job Match Score
                      </span>
                      <ScoreBreakdownTooltip
                        score={match.score}
                        breakdown={match.breakdown}
                        align="right"
                      />
                    </div>
                    {match.explanation && (
                      <p className="text-[11px] leading-4 text-slate-600">{match.explanation}</p>
                    )}
                  </div>
                )}
              </div>

              {/* Body Sections */}
              <div className="flex-1 divide-y divide-slate-100 p-5 text-xs">
                {/* Summary */}
                <section className="pb-4">
                  <h4 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Profile Summary
                  </h4>
                  <p className="leading-5 text-slate-600">
                    {c.profile_summary || 'No summary provided.'}
                  </p>
                </section>

                {/* Technical Skills */}
                <section className="py-4">
                  <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Technical Skills ({c.technical_skills.length})
                  </h4>
                  {c.technical_skills.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {c.technical_skills.map((sk) => {
                        const isShared = sharedSet.has(sk.toLowerCase())
                        return (
                          <span
                            key={`ts-${c.id}-${sk}`}
                            className={cn(
                              'rounded-md border px-2 py-0.5 text-[11px] font-medium',
                              isShared
                                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                                : 'border-slate-200 bg-slate-50 text-slate-700',
                            )}
                          >
                            {sk}
                          </span>
                        )
                      })}
                    </div>
                  ) : (
                    <p className="text-slate-400">None listed</p>
                  )}
                </section>

                {/* Tools */}
                <section className="py-4">
                  <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Tools & Platforms ({c.tools.length})
                  </h4>
                  {c.tools.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {c.tools.map((tool) => {
                        const isShared = sharedSet.has(tool.toLowerCase())
                        return (
                          <span
                            key={`tl-${c.id}-${tool}`}
                            className={cn(
                              'rounded-md border px-2 py-0.5 text-[11px] font-medium',
                              isShared
                                ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
                                : 'border-brand-100 bg-brand-50/50 text-brand-700',
                            )}
                          >
                            {tool}
                          </span>
                        )
                      })}
                    </div>
                  ) : (
                    <p className="text-slate-400">None listed</p>
                  )}
                </section>

                {/* Mobility & Compensation */}
                <section className="py-4 space-y-2">
                  <h4 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Availability & Mobility
                  </h4>
                  <div className="grid grid-cols-2 gap-2 text-slate-700">
                    <div className="rounded-lg bg-slate-50 p-2">
                      <span className="flex items-center gap-1 text-[10px] text-slate-400">
                        <Clock size={10} />
                        Notice Period
                      </span>
                      <p className="mt-0.5 font-semibold">
                        {c.notice_period_days != null ? `${c.notice_period_days} days` : '—'}
                      </p>
                    </div>
                    <div className="rounded-lg bg-slate-50 p-2">
                      <span className="text-[10px] text-slate-400">Relocation</span>
                      <p className="mt-0.5 font-semibold">
                        {c.open_to_relocate == null
                          ? '—'
                          : c.open_to_relocate
                            ? 'Open to relocate'
                            : 'Local only'}
                      </p>
                    </div>
                    {canWrite && (
                      <>
                        <div className="rounded-lg bg-slate-50 p-2">
                          <span className="flex items-center gap-1 text-[10px] text-slate-400">
                            <Wallet size={10} />
                            Current CTC
                          </span>
                          <p className="mt-0.5 font-semibold">
                            {formatCtc(c.current_ctc, c.ctc_currency)}
                          </p>
                        </div>
                        <div className="rounded-lg bg-slate-50 p-2">
                          <span className="flex items-center gap-1 text-[10px] text-slate-400">
                            <Wallet size={10} />
                            Expected CTC
                          </span>
                          <p className="mt-0.5 font-semibold">
                            {formatCtc(c.expected_ctc, c.ctc_currency)}
                          </p>
                        </div>
                      </>
                    )}
                  </div>
                </section>

                {/* Experience */}
                <section className="py-4">
                  <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                    Recent Experience ({c.work_experience.length})
                  </h4>
                  {c.work_experience.length > 0 ? (
                    <ul className="space-y-2.5">
                      {c.work_experience.slice(0, 3).map((w, i) => (
                        <li key={`we-${c.id}-${i}`} className="border-l-2 border-brand-200 pl-2.5">
                          <p className="font-semibold text-slate-900">{w.job_title}</p>
                          <p className="text-slate-600">{w.company}</p>
                          <p className="text-[11px] text-slate-400">
                            {w.start_date || '?'} — {w.end_date || 'Present'}
                          </p>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-slate-400">No roles recorded</p>
                  )}
                </section>

                {/* Education & Certifications */}
                <section className="pt-4 space-y-3">
                  <div>
                    <h4 className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                      <GraduationCap size={12} />
                      Education
                    </h4>
                    {c.education.length > 0 ? (
                      <ul className="space-y-1.5">
                        {c.education.map((ed, i) => (
                          <li key={`ed-${c.id}-${i}`}>
                            <p className="font-medium text-slate-800">{ed.degree}</p>
                            <p className="text-[11px] text-slate-500">
                              {ed.institution}
                              {ed.graduation_year ? ` · ${ed.graduation_year}` : ''}
                            </p>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-slate-400">None listed</p>
                    )}
                  </div>

                  {c.certifications.length > 0 && (
                    <div>
                      <h4 className="mb-1.5 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                        <Award size={12} />
                        Certifications ({c.certifications.length})
                      </h4>
                      <ul className="list-disc pl-4 space-y-0.5 text-slate-600">
                        {c.certifications.slice(0, 4).map((cert, i) => (
                          <li key={`cert-${c.id}-${i}`}>{cert}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </section>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
