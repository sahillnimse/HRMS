import { useState, useEffect, useCallback, useMemo } from 'react'
import { Link } from 'react-router-dom'
import {
  Briefcase,
  ChevronLeft,
  ChevronRight,
  Code2,
  Filter,
  Layers,
  LayoutGrid,
  List,
  Network,
  Search,
  Sparkles,
  Upload,
  Users,
  X,
} from 'lucide-react'
import { useCandidates } from '@/hooks/useCandidates'
import { useAuth } from '@/contexts/AuthContext'
import { PageHeader } from '@/components/layout/PageHeader'
import { CandidateCard } from '@/components/CandidateCard'
import { CandidateTable } from '@/components/CandidateTable'
import { SkillFilters } from '@/components/SkillFilters'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { cn, formatYears } from '@/lib/utils'

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
  const {
    candidates,
    stats,
    pagination,
    loading,
    statsLoading,
    error,
    fetchCandidates,
    fetchStats,
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
    fetchCandidates({
      page,
      page_size: 18,
      search: debouncedSearch.trim() || undefined,
      primary_domain: domain || undefined,
      skills: skills.length ? skills.join(',') : undefined,
      min_years: minYears !== '' ? parseFloat(minYears) : undefined,
      max_years: maxYears !== '' ? parseFloat(maxYears) : undefined,
    })
  }, [fetchCandidates, page, debouncedSearch, domain, skills, minYears, maxYears])

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
    setPage(1)
  }

  const toggleSkill = (skill: string) => {
    setPage(1)
    setSkills((prev) =>
      prev.includes(skill) ? prev.filter((s) => s !== skill) : [...prev, skill],
    )
  }

  const topDomain = stats?.domains[0]
  const topSkill = stats?.top_skills[0]
  const isEmptyDatabase = !loading && !statsLoading && (stats?.total ?? 0) === 0 && activeFilterCount === 0

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Talent Intelligence"
        title="Candidate Dashboard"
        description="Search structured candidate dossiers, inspect career networks, and filter your talent pool by skills, domain, and seniority."
        actions={
          canWrite ? (
            <Button asChild size="lg" className="shadow-glow">
              <Link to="/upload">
                <Upload size={17} />
                Upload Resume
              </Link>
            </Button>
          ) : undefined
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
            iconTint: 'bg-brand-50 text-brand-600',
          },
          {
            label: 'Avg. Experience',
            value: stats ? formatYears(stats.avg_years_experience) : '0 yrs',
            badge: 'Across saved pool',
            badgeTone: 'secondary',
            icon: Briefcase,
            iconTint: 'bg-sky-50 text-sky-600',
          },
          {
            label: 'Active Domains',
            value: stats ? String(stats.domains.length) : '0',
            badge: topDomain ? `Top: ${topDomain.name}` : 'No domains yet',
            badgeTone: topDomain ? 'brand' : 'secondary',
            icon: Layers,
            iconTint: 'bg-violet-50 text-violet-600',
          },
          {
            label: 'Most Common Skill',
            value: topSkill ? topSkill.name : '—',
            badge: topSkill ? `${topSkill.count} candidate${topSkill.count === 1 ? '' : 's'}` : 'Upload CV to map',
            badgeTone: topSkill ? 'brand' : 'secondary',
            icon: Code2,
            iconTint: 'bg-emerald-50 text-emerald-600',
          },
        ].map((kpi) => {
          const Icon = kpi.icon
          return (
            <div
              key={kpi.label}
              className="rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card transition hover:border-slate-300/80"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  {kpi.label}
                </span>
                <span
                  className={cn(
                    'flex h-9 w-9 items-center justify-center rounded-xl',
                    kpi.iconTint,
                  )}
                >
                  <Icon size={17} />
                </span>
              </div>
              {statsLoading && !stats ? (
                <div className="skeleton mt-3 h-8 w-24" />
              ) : (
                <p className="mt-2.5 truncate text-2xl font-bold tracking-tight text-slate-900">
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
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-100">
                      <div
                        className={cn(
                          'h-full rounded-full transition-all',
                          active ? 'bg-brand-600' : 'bg-brand-400 group-hover:bg-brand-500',
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
              {availableSkills.length > 0 && (
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
              {activeFilterCount > 0 && (
                <Button type="button" variant="ghost" size="sm" onClick={clearAllFilters}>
                  <X size={14} />
                  Reset
                </Button>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-12">
            <div className="relative md:col-span-5">
              <Search
                size={15}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name, email, or domain…"
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
        </CardContent>
      </Card>

      {/* Results Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <span className="font-semibold text-slate-900">{pagination.total}</span>
          <span>candidate{pagination.total === 1 ? '' : 's'}</span>
          {activeFilterCount > 0 && <span className="text-slate-400">matching filters</span>}
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
      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-800">
          {error}
        </div>
      )}

      {/* Loading Skeletons */}
      {loading && (
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
              <div className="rounded-2xl border border-brand-100 bg-gradient-to-br from-brand-50/70 via-white to-violet-50/70 p-5 bg-dots">
                <div className="mb-3 flex items-center justify-between text-xs font-semibold text-brand-700">
                  <span className="inline-flex items-center gap-1.5">
                    <Network size={14} />
                    Live Network Preview
                  </span>
                  <span className="rounded-full bg-white px-2 py-0.5 text-[11px] text-slate-500 shadow-sm">
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
                    stroke="#60a5fa"
                    strokeWidth={1.5}
                    strokeDasharray="4 4"
                  />
                  <g>
                    <circle cx="180" cy="95" r="26" fill="#4f46e5" />
                    <text x="180" y="99" textAnchor="middle" fill="#fff" fontSize="11" fontWeight="700">
                      CV
                    </text>

                    <circle cx="72" cy="48" r="18" fill="#f0f9ff" stroke="#0284c7" strokeWidth="1.8" />
                    <text x="72" y="52" textAnchor="middle" fill="#0c4a6e" fontSize="9" fontWeight="700">
                      ROLE
                    </text>

                    <circle cx="64" cy="142" r="16" fill="#fffbeb" stroke="#d97706" strokeWidth="1.8" />
                    <text x="64" y="146" textAnchor="middle" fill="#78350f" fontSize="9" fontWeight="700">
                      EDU
                    </text>

                    <circle cx="292" cy="45" r="17" fill="#f5f3ff" stroke="#7c3aed" strokeWidth="1.8" />
                    <text x="292" y="49" textAnchor="middle" fill="#4c1d95" fontSize="9" fontWeight="700">
                      TECH
                    </text>

                    <circle cx="305" cy="108" r="16" fill="#ecfdf5" stroke="#059669" strokeWidth="1.8" />
                    <text x="305" y="112" textAnchor="middle" fill="#064e3b" fontSize="9" fontWeight="700">
                      TOOL
                    </text>

                    <circle cx="255" cy="158" r="15" fill="#fff1f2" stroke="#e11d48" strokeWidth="1.8" />
                    <text x="255" y="162" textAnchor="middle" fill="#881337" fontSize="9" fontWeight="700">
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
      {!loading && !isEmptyDatabase && candidates.length === 0 && (
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
      {!loading && candidates.length > 0 && view === 'grid' && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {candidates.map((c) => (
            <CandidateCard key={c.id} candidate={c} />
          ))}
        </div>
      )}

      {!loading && candidates.length > 0 && view === 'table' && (
        <CandidateTable candidates={candidates} />
      )}

      {/* Pagination */}
      {!loading && pagination.pages > 1 && (
        <div className="flex items-center justify-between rounded-2xl border bg-white px-5 py-3 shadow-card">
          <p className="text-xs text-slate-500">
            Page <span className="font-semibold text-slate-900">{pagination.page}</span> of{' '}
            <span className="font-semibold text-slate-900">{pagination.pages}</span>
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={pagination.page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft size={15} />
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={pagination.page >= pagination.pages}
              onClick={() => setPage((p) => Math.min(pagination.pages, p + 1))}
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
