import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock,
  Filter,
  GitBranch,
  RefreshCw,
  SlidersHorizontal,
  TrendingUp,
  Users,
} from 'lucide-react'
import { api, getErrorMessage } from '@/lib/api'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/lib/utils'
import type {
  FunnelAnalytics,
  JobItem,
  SourcesAnalytics,
  StuckCandidatesAnalytics,
  TimeInStageAnalytics,
  TimeToHireAnalytics,
} from '@/types'

const STAGE_LABELS: Record<string, string> = {
  applied: 'Applied',
  screened: 'Screened',
  interview: 'Interview',
  offer: 'Offer',
  hired: 'Hired',
  rejected: 'Rejected',
}

const STAGE_BAR_COLORS: Record<string, string> = {
  applied: 'from-brand-500 to-brand-400',
  screened: 'from-teal-500 to-cyan-400',
  interview: 'from-sky-500 to-brand-500',
  offer: 'from-amber-500 to-orange-400',
  hired: 'from-emerald-600 to-emerald-400',
}

const STAGE_BADGE_VARIANT: Record<string, 'brand' | 'secondary' | 'warning' | 'success' | 'destructive' | 'outline'> = {
  applied: 'outline',
  screened: 'secondary',
  interview: 'brand',
  offer: 'warning',
  hired: 'success',
  rejected: 'destructive',
}

function formatDays(val: number | null | undefined): string {
  if (val === null || val === undefined) return '—'
  return `${val.toFixed(1)}d`
}

function isoDateDaysAgo(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

export default function AnalyticsPage() {
  const { blindMode } = useBlindMode()

  const [jobs, setJobs] = useState<JobItem[]>([])
  const [jobId, setJobId] = useState<string>('')
  const [startDate, setStartDate] = useState<string>('')
  const [endDate, setEndDate] = useState<string>('')

  const [showThresholdControls, setShowThresholdControls] = useState(false)
  const [appliedDays, setAppliedDays] = useState<string>('7')
  const [screenedDays, setScreenedDays] = useState<string>('7')
  const [interviewDays, setInterviewDays] = useState<string>('10')
  const [offerDays, setOfferDays] = useState<string>('7')

  const [funnel, setFunnel] = useState<FunnelAnalytics | null>(null)
  const [timeInStage, setTimeInStage] = useState<TimeInStageAnalytics | null>(null)
  const [timeToHire, setTimeToHire] = useState<TimeToHireAnalytics | null>(null)
  const [sources, setSources] = useState<SourcesAnalytics | null>(null)
  const [stuck, setStuck] = useState<StuckCandidatesAnalytics | null>(null)

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    api
      .get<JobItem[]>('/jobs')
      .then((res) => {
        if (active) setJobs(res.data || [])
      })
      .catch(() => {
        // Non-blocking: job filter simply stays on "All jobs"
      })
    return () => {
      active = false
    }
  }, [])

  const fetchAnalytics = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const commonParams: Record<string, string | number | boolean> = {}
      if (jobId) commonParams.job_id = jobId
      if (startDate) commonParams.start_date = startDate
      if (endDate) commonParams.end_date = endDate

      const stuckParams: Record<string, string | number | boolean> = {
        ...commonParams,
        blind: blindMode,
      }
      const parsedApplied = Number(appliedDays)
      const parsedScreened = Number(screenedDays)
      const parsedInterview = Number(interviewDays)
      const parsedOffer = Number(offerDays)
      if (Number.isFinite(parsedApplied) && parsedApplied >= 1) stuckParams.applied_days = parsedApplied
      if (Number.isFinite(parsedScreened) && parsedScreened >= 1) stuckParams.screened_days = parsedScreened
      if (Number.isFinite(parsedInterview) && parsedInterview >= 1) stuckParams.interview_days = parsedInterview
      if (Number.isFinite(parsedOffer) && parsedOffer >= 1) stuckParams.offer_days = parsedOffer

      const [funnelRes, tisRes, tthRes, srcRes, stuckRes] = await Promise.all([
        api.get<FunnelAnalytics>('/analytics/funnel', { params: commonParams }),
        api.get<TimeInStageAnalytics>('/analytics/time-in-stage', { params: commonParams }),
        api.get<TimeToHireAnalytics>('/analytics/time-to-hire', { params: commonParams }),
        api.get<SourcesAnalytics>('/analytics/sources', { params: commonParams }),
        api.get<StuckCandidatesAnalytics>('/analytics/stuck', { params: stuckParams }),
      ])

      setFunnel(funnelRes.data)
      setTimeInStage(tisRes.data)
      setTimeToHire(tthRes.data)
      setSources(srcRes.data)
      setStuck(stuckRes.data)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load hiring analytics.'))
    } finally {
      setLoading(false)
    }
  }, [jobId, startDate, endDate, blindMode, appliedDays, screenedDays, interviewDays, offerDays])

  useEffect(() => {
    void fetchAnalytics()
  }, [fetchAnalytics])

  const maxFunnelReached = useMemo(() => {
    if (!funnel?.stages.length) return 1
    return Math.max(1, ...funnel.stages.map((s) => s.reached_count))
  }, [funnel])

  const maxStageDays = useMemo(() => {
    if (!timeInStage?.stages.length) return 1
    return Math.max(
      1,
      ...timeInStage.stages.map((s) => Math.max(s.avg_days ?? 0, s.median_days ?? 0)),
    )
  }, [timeInStage])

  const maxSourceVolume = useMemo(() => {
    if (!sources?.sources.length) return 1
    return Math.max(1, ...sources.sources.map((s) => Math.max(s.candidates_count, s.applications_count)))
  }, [sources])

  const applyRangePreset = (days: number | null) => {
    if (days === null) {
      setStartDate('')
      setEndDate('')
    } else {
      setStartDate(isoDateDaysAgo(days))
      setEndDate(new Date().toISOString().slice(0, 10))
    }
  }

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        eyebrow="Hiring Intelligence"
        title="Hiring Analytics"
        description="Live funnel conversion, stage velocity, candidate source performance, and SLA bottleneck alerts derived directly from pipeline stage history."
        actions={
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setShowThresholdControls((prev) => !prev)}
            >
              <SlidersHorizontal size={15} />
              Stuck SLA Thresholds
            </Button>
            <Button variant="default" size="sm" onClick={() => void fetchAnalytics()} disabled={loading}>
              <RefreshCw size={15} className={cn(loading && 'animate-spin')} />
              Refresh
            </Button>
          </>
        }
      />

      {/* Filter Bar */}
      <Card className="border-stone-200/80 bg-white/95 shadow-soft">
        <CardContent className="p-4">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
            <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <label
                  htmlFor="analytics-job"
                  className="mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-slate-500"
                >
                  <Filter size={12} className="text-brand-600" />
                  Job Requisition
                </label>
                <select
                  id="analytics-job"
                  value={jobId}
                  onChange={(e) => setJobId(e.target.value)}
                  className="w-full rounded-xl border border-stone-200 bg-stone-50/60 px-3 py-2 text-sm text-slate-800 transition focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-4 focus:ring-brand-100"
                >
                  <option value="">All Jobs</option>
                  {jobs.map((j) => (
                    <option key={j.id} value={j.id}>
                      {j.title} ({j.status})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label
                  htmlFor="analytics-start"
                  className="mb-1 block text-[11px] font-bold uppercase tracking-wider text-slate-500"
                >
                  From Date
                </label>
                <input
                  id="analytics-start"
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full rounded-xl border border-stone-200 bg-stone-50/60 px-3 py-2 text-sm text-slate-800 transition focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-4 focus:ring-brand-100"
                />
              </div>
              <div>
                <label
                  htmlFor="analytics-end"
                  className="mb-1 block text-[11px] font-bold uppercase tracking-wider text-slate-500"
                >
                  To Date
                </label>
                <input
                  id="analytics-end"
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full rounded-xl border border-stone-200 bg-stone-50/60 px-3 py-2 text-sm text-slate-800 transition focus:border-brand-400 focus:bg-white focus:outline-none focus:ring-4 focus:ring-brand-100"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                onClick={() => applyRangePreset(30)}
                className="rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800"
              >
                Last 30d
              </button>
              <button
                type="button"
                onClick={() => applyRangePreset(90)}
                className="rounded-lg border border-stone-200 bg-stone-50 px-2.5 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-800"
              >
                Last 90d
              </button>
              <button
                type="button"
                onClick={() => {
                  setJobId('')
                  applyRangePreset(null)
                }}
                className="rounded-lg border border-stone-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-500 transition hover:border-stone-300 hover:text-slate-900"
              >
                Reset
              </button>
            </div>
          </div>

          {showThresholdControls && (
            <div className="mt-4 border-t border-stone-100 pt-4 animate-fade-in">
              <p className="mb-2.5 text-xs font-semibold text-slate-600">
                Stuck-candidate alert thresholds (days in stage before flagging):
              </p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                {[
                  { label: 'Applied (days)', value: appliedDays, setter: setAppliedDays },
                  { label: 'Screened (days)', value: screenedDays, setter: setScreenedDays },
                  { label: 'Interview (days)', value: interviewDays, setter: setInterviewDays },
                  { label: 'Offer (days)', value: offerDays, setter: setOfferDays },
                ].map((item) => (
                  <label key={item.label} className="block">
                    <span className="text-[11px] font-medium text-slate-500">{item.label}</span>
                    <input
                      type="number"
                      min={1}
                      max={365}
                      value={item.value}
                      onChange={(e) => item.setter(e.target.value)}
                      className="mt-1 w-full rounded-xl border border-stone-200 bg-white px-3 py-1.5 text-sm font-semibold text-slate-800 focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-100"
                    />
                  </label>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-2xl border border-coral-200 bg-coral-50 px-4 py-3 text-sm font-medium text-coral-700">
          {error}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Card className="border-stone-200/80 bg-white shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card animate-fade-in-up">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Total Applications
                </p>
                <p className="mt-2 font-display text-3xl font-bold text-slate-900">
                  {loading ? '—' : (funnel?.total_applications ?? 0)}
                </p>
              </div>
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
                <Users size={19} />
              </span>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              <span className="font-semibold text-brand-700">{funnel?.active_applications ?? 0}</span> active
              {' · '}
              <span className="font-semibold text-slate-700">{funnel?.rejected_count ?? 0}</span> rejected
            </p>
          </CardContent>
        </Card>

        <Card className="border-stone-200/80 bg-white shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card animate-fade-in-up">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Overall Hire Rate
                </p>
                <p className="mt-2 font-display text-3xl font-bold text-emerald-700">
                  {loading ? '—' : `${(funnel?.overall_hire_rate_pct ?? 0).toFixed(1)}%`}
                </p>
              </div>
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
                <TrendingUp size={19} />
              </span>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              <span className="font-semibold text-emerald-700">{funnel?.hired_count ?? 0}</span> hired out of{' '}
              {funnel?.total_applications ?? 0} applications
            </p>
          </CardContent>
        </Card>

        <Card className="border-stone-200/80 bg-white shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card animate-fade-in-up">
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Median Time to Hire
                </p>
                <p className="mt-2 font-display text-3xl font-bold text-slate-900">
                  {loading ? '—' : formatDays(timeToHire?.median_days)}
                </p>
              </div>
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-50 text-sky-600">
                <Clock size={19} />
              </span>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Avg {formatDays(timeToHire?.avg_days)}
              {timeToHire && timeToHire.hired_count > 0
                ? ` · Range ${formatDays(timeToHire.min_days)}–${formatDays(timeToHire.max_days)}`
                : ' · No hires in period'}
            </p>
          </CardContent>
        </Card>

        <Card
          className={cn(
            'border-stone-200/80 bg-white shadow-soft transition-all duration-200 hover:-translate-y-0.5 hover:shadow-card animate-fade-in-up',
            (stuck?.total_stuck ?? 0) > 0 && 'border-coral-200/90 bg-gradient-to-br from-white to-coral-50/40',
          )}
        >
          <CardContent className="p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Stuck Candidates
                </p>
                <p
                  className={cn(
                    'mt-2 font-display text-3xl font-bold',
                    (stuck?.total_stuck ?? 0) > 0 ? 'text-coral-600' : 'text-slate-900',
                  )}
                >
                  {loading ? '—' : (stuck?.total_stuck ?? 0)}
                </p>
              </div>
              <span
                className={cn(
                  'flex h-10 w-10 items-center justify-center rounded-xl',
                  (stuck?.total_stuck ?? 0) > 0
                    ? 'bg-coral-100 text-coral-600'
                    : 'bg-emerald-50 text-emerald-600',
                )}
              >
                {(stuck?.total_stuck ?? 0) > 0 ? (
                  <AlertTriangle size={19} />
                ) : (
                  <CheckCircle2 size={19} />
                )}
              </span>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              {(stuck?.total_stuck ?? 0) > 0
                ? 'Active applications exceeding stage SLA'
                : 'No active candidates past stage SLA'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Funnel + Time in Stage (2-column) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Funnel Bars */}
        <Card className="border-stone-200/80 bg-white shadow-soft lg:col-span-7">
          <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-stone-100 pb-4">
            <div>
              <CardTitle className="flex items-center gap-2 text-base">
                <BarChart3 size={17} className="text-brand-600" />
                Hiring Funnel Conversion
              </CardTitle>
              <p className="mt-0.5 text-xs text-slate-500">
                Cumulative candidates reaching each stage from ApplicationEvent history
              </p>
            </div>
            {funnel && (
              <Badge variant="outline" className="text-[11px]">
                {funnel.rejected_count} rejected
              </Badge>
            )}
          </CardHeader>
          <CardContent className="p-5">
            {loading ? (
              <div className="space-y-4">
                {[1, 2, 3, 4, 5].map((i) => (
                  <div key={i} className="h-11 animate-pulse rounded-xl bg-stone-100" />
                ))}
              </div>
            ) : !funnel || funnel.total_applications === 0 ? (
              <p className="py-10 text-center text-sm text-slate-500">
                No applications recorded for the selected filters yet.
              </p>
            ) : (
              <div className="space-y-4">
                {funnel.stages.map((stage) => {
                  const widthPct = Math.max(
                    stage.reached_count > 0 ? 6 : 0,
                    Math.round((stage.reached_count / maxFunnelReached) * 100),
                  )
                  const barColor = STAGE_BAR_COLORS[stage.stage] || 'from-brand-500 to-brand-400'
                  return (
                    <div key={stage.stage} className="space-y-1.5">
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-slate-800">
                            {STAGE_LABELS[stage.stage] || stage.stage}
                          </span>
                          <span className="rounded-md bg-stone-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-500">
                            {stage.current_count} currently here
                          </span>
                        </div>
                        <div className="flex items-center gap-3 tabular-nums">
                          {stage.conversion_from_previous_pct !== null && (
                            <span className="text-[11px] font-medium text-slate-500">
                              Step: <strong className="text-slate-700">{stage.conversion_from_previous_pct}%</strong>
                            </span>
                          )}
                          <span className="font-bold text-slate-900">
                            {stage.reached_count}{' '}
                            <span className="font-normal text-slate-400">
                              ({stage.conversion_from_applied_pct ?? 0}%)
                            </span>
                          </span>
                        </div>
                      </div>
                      <div className="h-3.5 w-full overflow-hidden rounded-full bg-stone-100">
                        <div
                          className={cn(
                            'h-full rounded-full bg-gradient-to-r transition-all duration-500 ease-out',
                            barColor,
                          )}
                          style={{ width: `${widthPct}%` }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Time in Stage */}
        <Card className="border-stone-200/80 bg-white shadow-soft lg:col-span-5">
          <CardHeader className="border-b border-stone-100 pb-4">
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock size={17} className="text-sky-600" />
              Time in Stage
            </CardTitle>
            <p className="mt-0.5 text-xs text-slate-500">
              Completed stage transitions (median &amp; average days)
            </p>
          </CardHeader>
          <CardContent className="p-5">
            {loading ? (
              <div className="space-y-4">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-12 animate-pulse rounded-xl bg-stone-100" />
                ))}
              </div>
            ) : !timeInStage ? null : (
              <div className="space-y-4">
                {timeInStage.stages.map((item) => {
                  const avgPct =
                    item.avg_days !== null
                      ? Math.max(6, Math.round((item.avg_days / maxStageDays) * 100))
                      : 0
                  const medPct =
                    item.median_days !== null
                      ? Math.max(6, Math.round((item.median_days / maxStageDays) * 100))
                      : 0
                  return (
                    <div
                      key={item.stage}
                      className="rounded-xl border border-stone-100 bg-stone-50/60 p-3"
                    >
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="font-semibold text-slate-800">
                          {STAGE_LABELS[item.stage] || item.stage}
                        </span>
                        <span className="text-[11px] text-slate-500">
                          {item.sample_count} transition{item.sample_count === 1 ? '' : 's'}
                        </span>
                      </div>
                      {item.sample_count === 0 ? (
                        <p className="mt-2 text-xs text-slate-400">No completed transitions yet</p>
                      ) : (
                        <div className="mt-2 space-y-1.5">
                          <div className="flex items-center gap-2">
                            <span className="w-12 text-[11px] font-medium text-slate-500">Median</span>
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-stone-200/80">
                              <div
                                className="h-full rounded-full bg-brand-500 transition-all duration-500"
                                style={{ width: `${medPct}%` }}
                              />
                            </div>
                            <span className="w-11 text-right text-xs font-bold tabular-nums text-slate-800">
                              {formatDays(item.median_days)}
                            </span>
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="w-12 text-[11px] font-medium text-slate-500">Avg</span>
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-stone-200/80">
                              <div
                                className="h-full rounded-full bg-sky-400 transition-all duration-500"
                                style={{ width: `${avgPct}%` }}
                              />
                            </div>
                            <span className="w-11 text-right text-xs font-semibold tabular-nums text-slate-600">
                              {formatDays(item.avg_days)}
                            </span>
                          </div>
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

      {/* Candidate Sources Breakdown */}
      <Card className="border-stone-200/80 bg-white shadow-soft">
        <CardHeader className="flex flex-row items-center justify-between gap-2 border-b border-stone-100 pb-4">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <GitBranch size={17} className="text-brand-600" />
              Candidate Sources
            </CardTitle>
            <p className="mt-0.5 text-xs text-slate-500">
              Pipeline volume and hire efficiency grouped by candidate source
            </p>
          </div>
          {sources && (
            <Badge variant="brand" className="text-[11px]">
              {sources.total_candidates} candidates
            </Badge>
          )}
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-9 animate-pulse rounded-xl bg-stone-100" />
              ))}
            </div>
          ) : !sources || sources.sources.length === 0 ? (
            <p className="py-8 text-center text-sm text-slate-500">No source data available.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-stone-100 text-sm">
                <thead className="bg-stone-50/80 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-5 py-3">Source</th>
                    <th className="px-4 py-3 text-right">Candidates</th>
                    <th className="px-4 py-3 text-right">Applications</th>
                    <th className="px-4 py-3 text-right">Screened</th>
                    <th className="px-4 py-3 text-right">Interviewed</th>
                    <th className="px-4 py-3 text-right">Hired</th>
                    <th className="px-5 py-3 text-right">Hire Rate</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {sources.sources.map((src) => {
                    const volPct = Math.max(
                      6,
                      Math.round(
                        (Math.max(src.candidates_count, src.applications_count) / maxSourceVolume) * 100,
                      ),
                    )
                    return (
                      <tr key={src.source} className="transition hover:bg-stone-50/70">
                        <td className="px-5 py-3.5">
                          <div className="flex items-center gap-3">
                            <span className="font-semibold capitalize text-slate-900">
                              {src.source.replace(/_/g, ' ')}
                            </span>
                            <div className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-stone-100 sm:block">
                              <div
                                className="h-full rounded-full bg-brand-500"
                                style={{ width: `${volPct}%` }}
                              />
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3.5 text-right tabular-nums text-slate-700">
                          {src.candidates_count}
                        </td>
                        <td className="px-4 py-3.5 text-right font-semibold tabular-nums text-slate-900">
                          {src.applications_count}
                        </td>
                        <td className="px-4 py-3.5 text-right tabular-nums text-slate-600">
                          {src.screened_count}
                        </td>
                        <td className="px-4 py-3.5 text-right tabular-nums text-slate-600">
                          {src.interview_count}
                        </td>
                        <td className="px-4 py-3.5 text-right font-semibold tabular-nums text-emerald-700">
                          {src.hired_count}
                        </td>
                        <td className="px-5 py-3.5 text-right tabular-nums">
                          <Badge
                            variant={src.hire_rate_pct > 0 ? 'success' : 'outline'}
                            className="text-[11px]"
                          >
                            {src.hire_rate_pct.toFixed(1)}%
                          </Badge>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Stuck Candidates Table */}
      <Card className="border-stone-200/80 bg-white shadow-soft">
        <CardHeader className="flex flex-col gap-2 border-b border-stone-100 pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <CardTitle className="flex items-center gap-2 text-base">
              <AlertTriangle
                size={17}
                className={(stuck?.total_stuck ?? 0) > 0 ? 'text-coral-500' : 'text-emerald-600'}
              />
              Stuck Candidates
            </CardTitle>
            <p className="mt-0.5 text-xs text-slate-500">
              Active applications sitting in the same stage longer than configured SLA thresholds
            </p>
          </div>
          {stuck && (
            <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-slate-500">
              {Object.entries(stuck.thresholds).map(([stageKey, daysVal]) => (
                <span
                  key={stageKey}
                  className="rounded-lg border border-stone-200 bg-stone-50 px-2 py-0.5 font-medium"
                >
                  {STAGE_LABELS[stageKey] || stageKey}: ≥{daysVal}d
                </span>
              ))}
            </div>
          )}
        </CardHeader>
        <CardContent className="p-0">
          {loading ? (
            <div className="space-y-3 p-5">
              {[1, 2, 3].map((i) => (
                <div key={i} className="h-10 animate-pulse rounded-xl bg-stone-100" />
              ))}
            </div>
          ) : !stuck || stuck.items.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-50 text-emerald-600">
                <CheckCircle2 size={24} />
              </span>
              <p className="mt-3 text-sm font-semibold text-slate-900">
                No stuck candidates right now
              </p>
              <p className="mt-1 max-w-md text-xs text-slate-500">
                Every active application is within your stage SLA thresholds. Adjust thresholds
                above to audit tighter windows.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-stone-100 text-sm">
                <thead className="bg-stone-50/80 text-left text-[11px] font-bold uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-5 py-3">Candidate</th>
                    <th className="px-4 py-3">Job</th>
                    <th className="px-4 py-3">Stage</th>
                    <th className="px-4 py-3 text-right">Days in Stage</th>
                    <th className="px-4 py-3 text-right">SLA Limit</th>
                    <th className="px-5 py-3 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-100">
                  {stuck.items.map((row) => (
                    <tr key={row.application_id} className="transition hover:bg-coral-50/30">
                      <td className="px-5 py-3.5 font-semibold text-slate-900">
                        <Link
                          to={`/candidates/${row.candidate_id}`}
                          className="hover:text-brand-700 hover:underline"
                        >
                          {row.candidate_name}
                        </Link>
                      </td>
                      <td className="px-4 py-3.5 text-slate-600">
                        <Link
                          to={`/jobs/${row.job_id}`}
                          className="hover:text-brand-700 hover:underline"
                        >
                          {row.job_title}
                        </Link>
                      </td>
                      <td className="px-4 py-3.5">
                        <Badge
                          variant={STAGE_BADGE_VARIANT[row.stage] || 'outline'}
                          className="capitalize"
                        >
                          {STAGE_LABELS[row.stage] || row.stage}
                        </Badge>
                      </td>
                      <td className="px-4 py-3.5 text-right font-bold tabular-nums text-coral-600">
                        {row.days_in_stage.toFixed(1)}d
                      </td>
                      <td className="px-4 py-3.5 text-right tabular-nums text-slate-500">
                        {row.threshold_days}d
                      </td>
                      <td className="px-5 py-3.5 text-right">
                        <Link
                          to={`/jobs/${row.job_id}`}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:text-brand-800"
                        >
                          Open Pipeline
                          <ArrowRight size={13} />
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
