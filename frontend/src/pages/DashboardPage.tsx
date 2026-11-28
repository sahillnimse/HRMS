import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  Briefcase,
  Calendar,
  ChevronLeft,
  ChevronRight,
  Code2,
  FileSpreadsheet,
  Filter,
  Layers,
  LayoutGrid,
  List,
  Network,
  Search,
  Sparkles,
  Upload,
  Users,
  Wand2,
  X,
} from 'lucide-react'
import { useCandidates } from '@/hooks/useCandidates'
import { useAuth } from '@/contexts/AuthContext'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { useAddToast } from '@/components/ui/Toast'
import { api, downloadBlobFile, getErrorMessage } from '@/lib/api'
import { PageHeader } from '@/components/layout/PageHeader'
import { CandidateCard } from '@/components/CandidateCard'
import { CandidateTable } from '@/components/CandidateTable'
import { SkillFilters } from '@/components/SkillFilters'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { cn, formatYears } from '@/lib/utils'
import type {
  CandidateSearchItem,
  InterviewItem,
  NLSearchResponse,
  StuckCandidatesAnalytics,
} from '@/types'

const PRESET_DOMAINS = [
  'Software Engineering',
  'Data Science',
  'Product Management',
  'Digital Marketing',
  'Operations',
  'Design',
  'Sales',
  'Finance',
  'Human Resources',
]

export default function DashboardPage() {
  const { canWrite } = useAuth()
  const { blindMode } = useBlindMode()
  const addToast = useAddToast()
  const {
    candidates,
    stats,
    pagination,
    searchMeta,
    loading,
    statsLoading,
    error,
    fetchCandidates,
    searchCandidates,
    fetchStats,
    deleteCandidate,
  } = useCandidates()

  const [view, setView] = useState<'grid' | 'table'>('grid')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [domain, setDomain] = useState('')
  const [skills, setSkills] = useState<string[]>([])
  const [minYears, setMinYears] = useState('')
  const [maxYears, setMaxYears] = useState('')
  const [showSkillDrawer, setShowSkillDrawer] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<CandidateSearchItem | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [exportingXlsx, setExportingXlsx] = useState(false)
  const [upcomingInterviews, setUpcomingInterviews] = useState<InterviewItem[]>([])
  const [stuckSummary, setStuckSummary] = useState<StuckCandidatesAnalytics | null>(null)

  // Natural-language search mode
  const [nlMode, setNlMode] = useState(false)
  const [nlQuery, setNlQuery] = useState('')
  const [nlLoading, setNlLoading] = useState(false)
  const [nlError, setNlError] = useState<string | null>(null)
  const [nlResult, setNlResult] = useState<NLSearchResponse | null>(null)

  useEffect(() => {
    let active = true
    const params = blindMode ? { blind: true } : undefined
    Promise.all([
      api.get<InterviewItem[]>('/interviews/mine', { params }).catch(() => ({ data: [] as InterviewItem[] })),
      api.get<StuckCandidatesAnalytics>('/analytics/stuck', { params }).catch(() => ({ data: null })),
    ]).then(([ivRes, stuckRes]) => {
      if (!active) return
      const now = Date.now()
      const upcoming = (ivRes.data || []).filter(
        (iv) => iv.status === 'scheduled' && new Date(iv.scheduled_at).getTime() >= now - 3_600_000,
      )
      setUpcomingInterviews(upcoming)
      setStuckSummary(stuckRes.data)
    })
    return () => {
      active = false
    }
  }, [blindMode])

  // Debounce search text
  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 260)
    return () => window.clearTimeout(timer)
  }, [search])

  useEffect(() => {
    fetchStats()
  }, [fetchStats])

  const loadPage = useCallback(() => {
    const trimmed = debouncedSearch.trim()
    const common = {
      page,
      page_size: 18,
      primary_domain: domain || undefined,
      skills: skills.length ? skills.join(',') : undefined,
      min_years: minYears !== '' ? parseFloat(minYears) : undefined,
      max_years: maxYears !== '' ? parseFloat(maxYears) : undefined,
    }
    if (trimmed) {
      void searchCandidates({ ...common, q: trimmed })
    } else {
      void fetchCandidates(common)
    }
  }, [fetchCandidates, searchCandidates, page, debouncedSearch, domain, skills, minYears, maxYears])

  useEffect(() => {
    loadPage()
  }, [loadPage])

  const allDomains = useMemo(() => {
    const set = new Set<string>(PRESET_DOMAINS)
    stats?.domains.forEach((d) => set.add(d.name))
    candidates.forEach((c) => c.primary_domain && set.add(c.primary_domain))
    return Array.from(set).sort()
  }, [stats, candidates])

  const availableSkills = useMemo(() => {
    const set = new Set<string>(skills)
    stats?.top_skills.forEach((s) => set.add(s.name))
    candidates.forEach((c) => c.technical_skills.forEach((s) => set.add(s)))
    return Array.from(set).sort()
  }, [stats, candidates, skills])

  const activeFilterCount =
    (debouncedSearch.trim() ? 1 : 0) +
    (domain ? 1 : 0) +
    skills.length +
    (minYears !== '' ? 1 : 0) +
    (maxYears !== '' ? 1 : 0)

  const clearAllFilters = () => {
    setSearch('')
    setDebouncedSearch('')
    setDomain('')
    setSkills([])
    setMinYears('')
    setMaxYears('')
    setNlQuery('')
    setNlResult(null)
    setNlError(null)
    setPage(1)
  }

  const runNlSearch = useCallback(
    async (queryText: string, targetPage = 1) => {
      const trimmed = queryText.trim()
      if (!trimmed) {
        setNlResult(null)
        setNlError(null)
        return
      }
      setNlLoading(true)
      setNlError(null)
      try {
        const res = await api.post<NLSearchResponse>('/candidates/nl-search', {
          query: trimmed,
          page: targetPage,
          page_size: 18,
          blind: blindMode,
        })
        setNlResult(res.data)
      } catch (err) {
        setNlError(getErrorMessage(err, 'Natural-language search failed'))
      } finally {
        setNlLoading(false)
      }
    },
    [blindMode],
  )

  useEffect(() => {
    if (nlMode && nlResult?.original_query) {
      void runNlSearch(nlResult.original_query, nlResult.page)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blindMode])

  const toggleSkill = (skill: string) => {
    setPage(1)
    setSkills((prev) =>
      prev.includes(skill) ? prev.filter((s) => s !== skill) : [...prev, skill],
    )
  }

  const displayedCandidates = nlMode && nlResult ? nlResult.items : candidates
  const displayedTotal = nlMode && nlResult ? nlResult.total : pagination.total
  const displayedPage = nlMode && nlResult ? nlResult.page : pagination.page
  const displayedPages = nlMode && nlResult ? nlResult.pages : pagination.pages
  const isBusy = nlMode ? nlLoading : loading
  const activeError = nlMode ? nlError : error

  const topDomain = stats?.domains[0]
  const topSkill = stats?.top_skills[0]
  const isEmptyDatabase =
    !isBusy && !statsLoading && (stats?.total ?? 0) === 0 && activeFilterCount === 0 && !nlResult

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    const ok = await deleteCandidate(deleteTarget.id)
    setDeleting(false)
    if (ok) {
      addToast('Candidate deleted', 'success')
      setDeleteTarget(null)
      loadPage()
      void fetchStats()
    } else {
      addToast('Failed to delete candidate', 'error')
    }
  }

  const handleExportXlsx = async () => {
    try {
      setExportingXlsx(true)
      await downloadBlobFile(
        '/candidates/export/xlsx',
        { blind: blindMode },
        blindMode ? 'candidates-blind-shortlist.xlsx' : 'candidates-shortlist.xlsx',
      )
      addToast('Shortlist XLSX exported', 'success')
    } catch {
      addToast('Failed to export XLSX', 'error')
    } finally {
      setExportingXlsx(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Talent Intelligence"
        title="Candidate Dashboard"
        description="Search structured candidate dossiers, inspect career networks, and filter your talent pool by skills, domain, and seniority."
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" loading={exportingXlsx} onClick={() => void handleExportXlsx()}>
              <FileSpreadsheet size={15} />
              Export XLSX
            </Button>
            {canWrite && (
              <Button asChild size="lg" className="shadow-glow">
                <Link to="/upload">
                  <Upload size={17} />
                  Upload Resume
                </Link>
              </Button>
            )}
          </div>
        }
      />

      {/* KPI Metrics Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          {
            label: 'Total Candidates',
            value: stats ? String(stats.total) : '0',
            badge:
              stats && stats.added_this_week > 0
                ? `+${stats.added_this_week} this week`
                : 'Ready to grow',
            badgeTone: stats && stats.added_this_week > 0 ? 'success' : 'secondary',
            icon: Users,
            iconTint: 'bg-brand-50 text-brand-600 ring-1 ring-brand-100',
            accentBar: 'from-brand-500 to-teal-400',
            stagger: 'stagger-1',
          },
          {
            label: 'Avg. Experience',
            value: stats ? formatYears(stats.avg_years_experience) : '0 yrs',
            badge: 'Across saved pool',
            badgeTone: 'secondary',
            icon: Briefcase,
            iconTint: 'bg-coral-50 text-coral-600 ring-1 ring-coral-100',
            accentBar: 'from-coral-400 to-amber-400',
            stagger: 'stagger-2',
          },
          {
            label: 'Active Domains',
            value: stats ? String(stats.domains.length) : '0',
            badge: topDomain ? `Top: ${topDomain.name}` : 'No domains yet',
            badgeTone: topDomain ? 'brand' : 'secondary',
            icon: Layers,
            iconTint: 'bg-amber-50 text-amber-600 ring-1 ring-amber-100',
            accentBar: 'from-amber-400 to-orange-400',
            stagger: 'stagger-3',
          },
          {
            label: 'Most Common Skill',
            value: topSkill ? topSkill.name : '—',
            badge: topSkill ? `${topSkill.count} candidate${topSkill.count === 1 ? '' : 's'}` : 'Upload CV to map',
            badgeTone: topSkill ? 'brand' : 'secondary',
            icon: Code2,
            iconTint: 'bg-sky-50 text-sky-600 ring-1 ring-sky-100',
            accentBar: 'from-sky-500 to-brand-400',
            stagger: 'stagger-4',
          },
        ].map((kpi) => {
          const Icon = kpi.icon
          return (
            <div
              key={kpi.label}
              className={cn(
                'group relative overflow-hidden rounded-2xl border border-stone-200/80 bg-white p-5 shadow-card card-interactive animate-fade-up',
                kpi.stagger,
              )}
            >
              <div
                className={cn(
                  'absolute inset-x-0 top-0 h-1 bg-gradient-to-r opacity-85 transition-opacity group-hover:opacity-100',
                  kpi.accentBar,
                )}
              />
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  {kpi.label}
                </span>
                <span
                  className={cn(
                    'flex h-10 w-10 items-center justify-center rounded-xl transition-transform duration-300 group-hover:scale-110',
                    kpi.iconTint,
                  )}
                >
                  <Icon size={18} />
                </span>
              </div>
              {statsLoading && !stats ? (
                <div className="skeleton mt-3 h-8 w-24" />
              ) : (
                <p className="mt-2.5 truncate font-display text-2xl font-bold tracking-tight text-slate-900">
                  {kpi.value}
                </p>
              )}
              <div className="mt-2.5">
                <Badge variant={kpi.badgeTone as 'brand' | 'success' | 'secondary'} className="max-w-full truncate">
                  {kpi.badge}
                </Badge>
              </div>
            </div>
          )
        })}
      </div>

      {/* Compact Action Strip: Upcoming Interviews & Stuck SLA Alerts */}
      {(upcomingInterviews.length > 0 || (stuckSummary?.total_stuck ?? 0) > 0) && (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 animate-fade-in">
          {upcomingInterviews.length > 0 && (
            <Link
              to="/interviews"
              className="group flex items-center justify-between gap-3 rounded-2xl border border-brand-200/80 bg-gradient-to-r from-brand-50/70 to-white px-4 py-3 shadow-sm transition hover:border-brand-300 hover:shadow-card"
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand-600 text-white">
                  <Calendar size={16} />
                </span>
                <div className="min-w-0">
                  <p className="text-xs font-bold text-slate-900">
                    {upcomingInterviews.length} Upcoming Interview
                    {upcomingInterviews.length === 1 ? '' : 's'}
                  </p>
                  <p className="truncate text-xs text-slate-600">
                    Next: {upcomingInterviews[0].round_name}
                    {upcomingInterviews[0].candidate_name
                      ? ` · ${upcomingInterviews[0].candidate_name}`
                      : ''}
                  </p>
                </div>
              </div>
              <ArrowRight
                size={15}
                className="shrink-0 text-brand-600 transition-transform group-hover:translate-x-0.5"
              />
            </Link>
          )}

          {(stuckSummary?.total_stuck ?? 0) > 0 && (
            <Link
              to="/analytics"
              className="group flex items-center justify-between gap-3 rounded-2xl border border-coral-200/80 bg-gradient-to-r from-coral-50/70 to-white px-4 py-3 shadow-sm transition hover:border-coral-300 hover:shadow-card"
            >
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-coral-500 text-white">
                  <AlertTriangle size={16} />
                </span>
                <div className="min-w-0">
                  <p className="text-xs font-bold text-slate-900">
                    {stuckSummary!.total_stuck} Stuck Candidate
                    {stuckSummary!.total_stuck === 1 ? '' : 's'} Past Stage SLA
                  </p>
                  <p className="truncate text-xs text-slate-600">
                    Longest: {stuckSummary!.items[0]?.candidate_name} ({stuckSummary!.items[0]?.days_in_stage.toFixed(0)}d in{' '}
                    {stuckSummary!.items[0]?.stage})
                  </p>
                </div>
              </div>
              <ArrowRight
                size={15}
                className="shrink-0 text-coral-600 transition-transform group-hover:translate-x-0.5"
              />
            </Link>
          )}
        </div>
      )}

      {/* Talent Pool Breakdown (shown when candidates exist) */}
      {stats && stats.total > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
          <Card className="lg:col-span-5">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Domain Distribution</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {stats.domains.slice(0, 4).map((d) => {
                const pct = Math.round((d.count / Math.max(1, stats.total)) * 100)
                const active = domain === d.name
                return (
                  <button
                    key={d.name}
                    type="button"
                    onClick={() => {
                      setPage(1)
                      setDomain((prev) => (prev === d.name ? '' : d.name))
                    }}
                    className="group block w-full text-left"
                  >
                    <div className="mb-1 flex items-center justify-between text-xs">
                      <span
                        className={cn(
                          'font-medium transition',
                          active ? 'text-brand-700' : 'text-slate-700 group-hover:text-brand-600',
                        )}
                      >
                        {d.name}
                      </span>
                      <span className="text-slate-500">
                        {d.count} ({pct}%)
                      </span>
                    </div>
                    <div className="h-2.5 w-full overflow-hidden rounded-full bg-stone-100">
                      <div
                        className={cn(
                          'h-full rounded-full animate-bar-grow transition-all',
                          active
                            ? 'bg-gradient-to-r from-brand-600 to-teal-500'
                            : 'bg-gradient-to-r from-brand-400 to-teal-400 group-hover:from-brand-500 group-hover:to-coral-400',
                        )}
                        style={{ width: `${Math.max(6, pct)}%` }}
                      />
                    </div>
                  </button>
                )
              })}
            </CardContent>
          </Card>

          <Card className="lg:col-span-7">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">Top Skills in Talent Pool</CardTitle>
                <span className="text-xs text-slate-400">Click any skill to filter</span>
              </div>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {stats.top_skills.slice(0, 14).map((s) => {
                  const active = skills.includes(s.name)
                  return (
                    <button
                      key={s.name}
                      type="button"
                      onClick={() => toggleSkill(s.name)}
                      className={cn(
                        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-medium transition',
                        active
                          ? 'border-brand-600 bg-brand-600 text-white shadow-sm'
                          : 'border-slate-200 bg-slate-50/70 text-slate-700 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700',
                      )}
                    >
                      <span>{s.name}</span>
                      <span
                        className={cn(
                          'rounded-full px-1.5 text-[10px] font-semibold',
                          active ? 'bg-white/20 text-white' : 'bg-slate-200/80 text-slate-600',
                        )}
                      >
                        {s.count}
                      </span>
                    </button>
                  )
                })}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Search & Filter Panel */}
      <Card>
        <CardHeader className="pb-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Filter size={16} className="text-brand-600" />
              <CardTitle className="text-sm">Search & Filters</CardTitle>
              {activeFilterCount > 0 && <Badge variant="brand">{activeFilterCount} active</Badge>}
            </div>

            <div className="flex items-center gap-2">
              <div className="inline-flex rounded-lg border border-slate-200 bg-slate-50 p-0.5">
                <button
                  type="button"
                  onClick={() => {
                    setNlMode(false)
                    setNlError(null)
                  }}
                  className={cn(
                    'rounded-md px-2.5 py-1 text-xs font-semibold transition',
                    !nlMode ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800',
                  )}
                >
                  Filters
                </button>
                <button
                  type="button"
                  onClick={() => setNlMode(true)}
                  className={cn(
                    'inline-flex items-center gap-1 rounded-md px-2.5 py-1 text-xs font-semibold transition',
                    nlMode ? 'bg-brand-600 text-white shadow-sm' : 'text-slate-500 hover:text-slate-800',
                  )}
                >
                  <Wand2 size={12} />
                  Natural Language
                </button>
              </div>
              {!nlMode && availableSkills.length > 0 && (
                <Button
                  type="button"
                  variant={showSkillDrawer || skills.length > 0 ? 'soft' : 'outline'}
                  size="sm"
                  onClick={() => setShowSkillDrawer((v) => !v)}
                >
                  <Code2 size={14} />
                  Skills{skills.length ? ` (${skills.length})` : ''}
                </Button>
              )}
              {(activeFilterCount > 0 || nlResult) && (
                <Button type="button" variant="ghost" size="sm" onClick={clearAllFilters}>
                  <X size={14} />
                  Reset
                </Button>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          {nlMode ? (
            <div className="space-y-3">
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  void runNlSearch(nlQuery, 1)
                }}
                className="flex flex-col gap-2 sm:flex-row"
              >
                <div className="relative flex-1">
                  <Wand2
                    size={15}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-brand-500"
                  />
                  <Input
                    value={nlQuery}
                    onChange={(e) => setNlQuery(e.target.value)}
                    placeholder='Try: "Python, 3+ yrs, Pune, notice < 30 days" or "React 2-5 years Bangalore"'
                    className="pl-9 pr-8"
                  />
                  {nlQuery && (
                    <button
                      type="button"
                      onClick={() => {
                        setNlQuery('')
                        setNlResult(null)
                        setNlError(null)
                      }}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      aria-label="Clear natural language query"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>
                <Button type="submit" loading={nlLoading} disabled={!nlQuery.trim()}>
                  <Search size={14} />
                  Search
                </Button>
              </form>

              {nlResult && (
                <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-brand-200/70 bg-brand-50/40 px-3 py-2 text-xs">
                  <span className="font-semibold text-brand-800">Parsed filters:</span>
                  {nlResult.parsed_filters.skills.map((sk) => (
                    <Badge key={`nl-sk-${sk}`} variant="brand">
                      Skill: {sk}
                    </Badge>
                  ))}
                  {nlResult.parsed_filters.min_years != null && (
                    <Badge variant="secondary">≥ {nlResult.parsed_filters.min_years} yrs</Badge>
                  )}
                  {nlResult.parsed_filters.max_years != null && (
                    <Badge variant="secondary">≤ {nlResult.parsed_filters.max_years} yrs</Badge>
                  )}
                  {nlResult.parsed_filters.city && (
                    <Badge variant="secondary">City: {nlResult.parsed_filters.city}</Badge>
                  )}
                  {nlResult.parsed_filters.max_notice_days != null && (
                    <Badge variant="secondary">
                      Notice ≤ {nlResult.parsed_filters.max_notice_days}d
                    </Badge>
                  )}
                  {nlResult.parsed_filters.primary_domain && (
                    <Badge variant="secondary">
                      Domain: {nlResult.parsed_filters.primary_domain}
                    </Badge>
                  )}
                  {nlResult.parsed_filters.semantic_query && (
                    <Badge variant="outline">Query: {nlResult.parsed_filters.semantic_query}</Badge>
                  )}
                  <span className="ml-auto text-[11px] text-slate-500">
                    via {nlResult.parser_mode === 'gemini' ? 'Gemini NL' : 'Deterministic NL'}
                  </span>
                </div>
              )}
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
                <div className="relative md:col-span-5">
                  <Search
                    size={15}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                  />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Hybrid search by name, skills, role, summary, or domain…"
                    className="pl-9 pr-8"
                  />
                  {search && (
                    <button
                      type="button"
                      onClick={() => setSearch('')}
                      className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                      aria-label="Clear search"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>

                <div className="md:col-span-3">
                  <Select
                    value={domain}
                    onChange={(e) => {
                      setDomain(e.target.value)
                      setPage(1)
                    }}
                  >
                    <option value="">All domains</option>
                    {allDomains.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </Select>
                </div>

                <div className="md:col-span-2">
                  <Input
                    type="number"
                    min={0}
                    value={minYears}
                    onChange={(e) => {
                      setMinYears(e.target.value)
                      setPage(1)
                    }}
                    placeholder="Min yrs"
                  />
                </div>

                <div className="md:col-span-2">
                  <Input
                    type="number"
                    min={0}
                    value={maxYears}
                    onChange={(e) => {
                      setMaxYears(e.target.value)
                      setPage(1)
                    }}
                    placeholder="Max yrs"
                  />
                </div>
              </div>

              {showSkillDrawer && availableSkills.length > 0 && (
                <SkillFilters
                  availableSkills={availableSkills}
                  selectedSkills={skills}
                  onToggleSkill={toggleSkill}
                  onClearSkills={() => {
                    setSkills([])
                    setPage(1)
                  }}
                />
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Results Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-600">
          <span className="font-semibold text-slate-900">{displayedTotal}</span>
          <span>candidate{displayedTotal === 1 ? '' : 's'}</span>
          {(activeFilterCount > 0 || (nlMode && nlResult)) && (
            <span className="text-slate-400">matching filters</span>
          )}
          {nlMode && nlResult ? (
            <Badge variant="brand" className="ml-1">
              <Wand2 size={11} />
              {nlResult.semantic_used ? 'NL + Semantic Hybrid' : 'NL Structured Search'}
            </Badge>
          ) : searchMeta.active ? (
            <Badge variant="brand" className="ml-1">
              <Sparkles size={11} />
              {searchMeta.semantic_used ? 'Hybrid Semantic + FTS' : 'Hybrid FTS + Fuzzy'}
            </Badge>
          ) : null}
        </div>

        <div className="inline-flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
          <button
            type="button"
            onClick={() => setView('grid')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition',
              view === 'grid'
                ? 'bg-brand-600 text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-900',
            )}
          >
            <LayoutGrid size={14} />
            Cards
          </button>
          <button
            type="button"
            onClick={() => setView('table')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition',
              view === 'table'
                ? 'bg-brand-600 text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-900',
            )}
          >
            <List size={14} />
            Table
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {activeError && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-800">
          {activeError}
        </div>
      )}

      {/* Loading Skeletons */}
      {isBusy && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="rounded-2xl border bg-white p-5 shadow-card">
              <div className="flex items-center gap-3">
                <div className="skeleton h-11 w-11 rounded-xl" />
                <div className="flex-1 space-y-2">
                  <div className="skeleton h-4 w-36" />
                  <div className="skeleton h-3 w-48" />
                </div>
              </div>
              <div className="mt-4 flex gap-2">
                <div className="skeleton h-5 w-24 rounded-full" />
                <div className="skeleton h-5 w-20 rounded-full" />
              </div>
              <div className="mt-4 flex gap-1.5">
                <div className="skeleton h-5 w-14" />
                <div className="skeleton h-5 w-16" />
                <div className="skeleton h-5 w-12" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* First-Time Empty Onboarding Hero */}
      {isEmptyDatabase && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-card animate-fade-in">
          <div className="grid grid-cols-1 items-center gap-8 p-8 lg:grid-cols-12 lg:p-10">
            <div className="space-y-4 lg:col-span-7">
              <Badge variant="brand">
                <Sparkles size={12} />
                Get Started
              </Badge>
              <h2 className="text-2xl font-bold tracking-tight text-slate-900">
                Turn any resume into a structured dossier & interactive skill network
              </h2>
              <p className="max-w-xl text-sm leading-6 text-slate-500">
                Upload a PDF or DOCX resume. HRMS AI parses work history, education, and skills,
                maps how skills connect to roles in an interactive network graph, and lets your HR
                team review before saving.
              </p>
              <div className="flex flex-wrap items-center gap-3 pt-2">
                <Button asChild size="lg" className="shadow-glow">
                  <Link to="/upload">
                    <Upload size={17} />
                    Upload First Resume
                  </Link>
                </Button>
              </div>
            </div>

            {/* Subtle light-theme mini network preview illustration */}
            <div className="lg:col-span-5">
              <div className="rounded-2xl border border-brand-200/70 mesh-hero p-5 bg-dots">
                <div className="mb-3 flex items-center justify-between text-xs font-semibold text-brand-700">
                  <span className="inline-flex items-center gap-1.5">
                    <Network size={14} />
                    Live Network Preview
                  </span>
                  <span className="rounded-full bg-white px-2.5 py-0.5 text-[11px] text-slate-500 shadow-sm">
                    Auto-generated on upload
                  </span>
                </div>
                <svg viewBox="0 0 360 190" className="w-full">
                  <g stroke="#cbd5e1" strokeWidth={1.5}>
                    <line x1="180" y1="95" x2="72" y2="48" />
                    <line x1="180" y1="95" x2="64" y2="142" />
                    <line x1="180" y1="95" x2="292" y2="45" />
                    <line x1="180" y1="95" x2="305" y2="108" />
                    <line x1="180" y1="95" x2="255" y2="158" />
                  </g>
                  <path
                    d="M 72 48 Q 182 18 292 45"
                    fill="none"
                    stroke="#0f9d8a"
                    strokeWidth={1.6}
                    strokeDasharray="4 4"
                    className="animate-dash"
                  />
                  <g>
                    <circle cx="180" cy="95" r="26" fill="#0d8274" />
                    <text x="180" y="99" textAnchor="middle" fill="#fff" fontSize="11" fontWeight="700">
                      CV
                    </text>

                    <circle cx="72" cy="48" r="18" fill="#edfaf7" stroke="#0f9d8a" strokeWidth="1.8" />
                    <text x="72" y="52" textAnchor="middle" fill="#0b685e" fontSize="9" fontWeight="700">
                      ROLE
                    </text>

                    <circle cx="64" cy="142" r="16" fill="#fffbeb" stroke="#d97706" strokeWidth="1.8" />
                    <text x="64" y="146" textAnchor="middle" fill="#78350f" fontSize="9" fontWeight="700">
                      EDU
                    </text>

                    <circle cx="292" cy="45" r="17" fill="#fff4f2" stroke="#f25c43" strokeWidth="1.8" />
                    <text x="292" y="49" textAnchor="middle" fill="#bc331d" fontSize="9" fontWeight="700">
                      TECH
                    </text>

                    <circle cx="305" cy="108" r="16" fill="#ecfdf5" stroke="#059669" strokeWidth="1.8" />
                    <text x="305" y="112" textAnchor="middle" fill="#064e3b" fontSize="9" fontWeight="700">
                      TOOL
                    </text>

                    <circle cx="255" cy="158" r="15" fill="#f0f9ff" stroke="#0284c7" strokeWidth="1.8" />
                    <text x="255" y="162" textAnchor="middle" fill="#075985" fontSize="9" fontWeight="700">
                      CERT
                    </text>
                  </g>
                </svg>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Filtered Empty State */}
      {!isBusy && !isEmptyDatabase && displayedCandidates.length === 0 && (
        <div className="rounded-2xl border bg-white p-12 text-center shadow-card">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
            <Search size={22} />
          </div>
          <h3 className="text-base font-semibold text-slate-900">No matching candidates</h3>
          <p className="mt-1 text-sm text-slate-500">
            Try widening your search query, domain, or skill filters.
          </p>
          <Button variant="outline" size="sm" onClick={clearAllFilters} className="mt-4">
            Reset all filters
          </Button>
        </div>
      )}

      {/* Candidate Cards / Table */}
      {!isBusy && displayedCandidates.length > 0 && view === 'grid' && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {displayedCandidates.map((c) => (
            <CandidateCard
              key={c.id}
              candidate={c}
              onDelete={canWrite ? setDeleteTarget : undefined}
            />
          ))}
        </div>
      )}

      {!isBusy && displayedCandidates.length > 0 && view === 'table' && (
        <CandidateTable
          candidates={displayedCandidates}
          onDelete={canWrite ? setDeleteTarget : undefined}
        />
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title={`Delete ${deleteTarget?.full_name || 'candidate'}?`}
        description="This permanently removes the candidate profile, parsed data, and stored resume file while retaining a PII-free audit entry."
        confirmLabel="Delete Candidate"
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* Pagination */}
      {!isBusy && displayedPages > 1 && (
        <div className="flex items-center justify-between rounded-2xl border bg-white px-5 py-3 shadow-card">
          <p className="text-xs text-slate-500">
            Page <span className="font-semibold text-slate-900">{displayedPage}</span> of{' '}
            <span className="font-semibold text-slate-900">{displayedPages}</span>
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={displayedPage <= 1}
              onClick={() => {
                if (nlMode && nlResult) {
                  void runNlSearch(nlResult.original_query, Math.max(1, displayedPage - 1))
                } else {
                  setPage((p) => Math.max(1, p - 1))
                }
              }}
            >
              <ChevronLeft size={15} />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={displayedPage >= displayedPages}
              onClick={() => {
                if (nlMode && nlResult) {
                  void runNlSearch(
                    nlResult.original_query,
                    Math.min(displayedPages, displayedPage + 1),
                  )
                } else {
                  setPage((p) => Math.min(displayedPages, p + 1))
                }
              }}
            >
              Next
              <ChevronRight size={15} />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
