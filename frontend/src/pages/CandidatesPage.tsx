import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  FileText,
  GitCompareArrows,
  LayoutGrid,
  List,
  Search,
  Sparkles,
  Upload,
  Users,
  X,
} from 'lucide-react'
import { useCandidates } from '@/hooks/useCandidates'
import { useAuth } from '@/contexts/AuthContext'
import { api, fetchResumeBlob } from '@/lib/api'
import { PageHeader } from '@/components/layout/PageHeader'
import { CandidateCard } from '@/components/CandidateCard'
import { CandidateTable } from '@/components/CandidateTable'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { cn, formatRelativeDate } from '@/lib/utils'
import type { PendingResumeItem, ResumeUploadResponse } from '@/types'

const PENDING_CACHE_KEY = 'hrms_pending_uploads'

function getCachedUploads(): Record<string, ResumeUploadResponse> {
  try {
    const raw = window.sessionStorage.getItem(PENDING_CACHE_KEY)
    return raw ? (JSON.parse(raw) as Record<string, ResumeUploadResponse>) : {}
  } catch {
    return {}
  }
}

export default function CandidatesPage() {
  const navigate = useNavigate()
  const { canWrite } = useAuth()
  const {
    candidates,
    stats,
    pagination,
    searchMeta,
    loading,
    error,
    fetchCandidates,
    searchCandidates,
    fetchStats,
  } = useCandidates()

  const [view, setView] = useState<'grid' | 'table'>('grid')
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [domain, setDomain] = useState('')
  const [pendingResumes, setPendingResumes] = useState<PendingResumeItem[]>([])
  const [openingId, setOpeningId] = useState<string | null>(null)
  const [compareIds, setCompareIds] = useState<string[]>([])

  const cachedUploads = useMemo(() => getCachedUploads(), [])

  useEffect(() => {
    const t = window.setTimeout(() => {
      setDebouncedSearch(search)
      setPage(1)
    }, 250)
    return () => window.clearTimeout(t)
  }, [search])

  useEffect(() => {
    fetchStats()
    api
      .get<PendingResumeItem[]>('/resumes/pending')
      .then((res) => setPendingResumes(res.data))
      .catch(() => {})
  }, [fetchStats])

  const loadCandidates = useCallback(() => {
    const trimmed = debouncedSearch.trim()
    if (trimmed) {
      void searchCandidates({
        page,
        page_size: 18,
        q: trimmed,
        primary_domain: domain || undefined,
      })
    } else {
      void fetchCandidates({
        page,
        page_size: 18,
        primary_domain: domain || undefined,
      })
    }
  }, [fetchCandidates, searchCandidates, page, debouncedSearch, domain])

  const toggleCompare = useCallback((id: string) => {
    setCompareIds((prev) => {
      if (prev.includes(id)) return prev.filter((item) => item !== id)
      if (prev.length >= 3) return prev
      return [...prev, id]
    })
  }, [])

  useEffect(() => {
    loadCandidates()
  }, [loadCandidates])

  const domains = useMemo(() => {
    const set = new Set<string>()
    stats?.domains.forEach((d) => set.add(d.name))
    candidates.forEach((c) => c.primary_domain && set.add(c.primary_domain))
    return Array.from(set).sort()
  }, [stats, candidates])

  const openPendingFile = async (item: PendingResumeItem) => {
    try {
      setOpeningId(item.id)
      const blob = await fetchResumeBlob(item.id, false)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } finally {
      setOpeningId(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Candidate Directory"
        title="Candidates"
        description="Browse every candidate whose profile and CV have been uploaded. Click any candidate to open their full profile dashboard, network graph, and saved resume."
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

      {/* Pending / Unsaved Uploaded Resumes (if any) */}
      {pendingResumes.length > 0 && (
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader className="pb-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Clock size={16} className="text-amber-600" />
                <CardTitle className="text-sm text-amber-950">
                  Uploaded CVs Pending Save ({pendingResumes.length})
                </CardTitle>
              </div>
              <span className="text-xs text-amber-800">
                Files saved in storage — open to view or finish reviewing to attach to a candidate
              </span>
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {pendingResumes.slice(0, 5).map((item) => {
              const cached = cachedUploads[item.id]
              return (
                <div
                  key={item.id}
                  className="flex flex-col gap-2 rounded-xl border border-amber-200/80 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-amber-50 text-amber-600">
                      <FileText size={17} />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-slate-900">
                        {cached?.parsed_data.full_name
                          ? `${cached.parsed_data.full_name} — ${item.original_filename}`
                          : item.original_filename}
                      </p>
                      <p className="text-xs text-slate-500">
                        {(item.file_size / 1024).toFixed(0)} KB · Uploaded{' '}
                        {formatRelativeDate(item.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      loading={openingId === item.id}
                      onClick={() => openPendingFile(item)}
                    >
                      <ExternalLink size={13} />
                      View CV
                    </Button>
                    {canWrite && cached && (
                      <Button
                        size="sm"
                        onClick={() => navigate('/review', { state: { upload: cached } })}
                      >
                        Resume Review & Save
                      </Button>
                    )}
                  </div>
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}

      {/* Search + Domain Filter + View Switcher */}
      <div className="flex flex-col gap-3 rounded-2xl border bg-white p-4 shadow-card sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-1 flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1 max-w-md">
            <Search
              size={15}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Hybrid search by name, skills, role, or domain…"
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

          <div className="w-full sm:w-52">
            <Select
              value={domain}
              onChange={(e) => {
                setDomain(e.target.value)
                setPage(1)
              }}
            >
              <option value="">All domains</option>
              {domains.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </Select>
          </div>

          <Badge variant="secondary" className="w-fit">
            {pagination.total} saved candidate{pagination.total === 1 ? '' : 's'}
          </Badge>
          {searchMeta.active && (
            <Badge variant="brand" className="w-fit">
              <Sparkles size={11} />
              {searchMeta.semantic_used ? 'Semantic + FTS' : 'Hybrid FTS'}
            </Badge>
          )}
        </div>

        <div className="inline-flex self-end rounded-xl border border-slate-200 bg-slate-50/70 p-1 sm:self-auto">
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

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-800">
          {error}
        </div>
      )}

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
            </div>
          ))}
        </div>
      )}

      {!loading && candidates.length === 0 && (
        <div className="rounded-2xl border bg-white p-12 text-center shadow-card">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-50 text-brand-600">
            <Users size={22} />
          </div>
          <h3 className="text-base font-semibold text-slate-900">
            {debouncedSearch || domain ? 'No matching candidates' : 'No saved candidates yet'}
          </h3>
          <p className="mt-1 text-sm text-slate-500">
            {debouncedSearch || domain
              ? 'Try clearing your search or domain filter.'
              : 'Upload a candidate resume to build their profile dashboard and save their CV.'}
          </p>
          {debouncedSearch || domain ? (
            <Button
              variant="outline"
              size="sm"
              className="mt-4"
              onClick={() => {
                setSearch('')
                setDebouncedSearch('')
                setDomain('')
                setPage(1)
              }}
            >
              Clear filters
            </Button>
          ) : canWrite ? (
            <Button asChild className="mt-5 shadow-glow">
              <Link to="/upload">
                <Upload size={16} />
                Upload First Resume
              </Link>
            </Button>
          ) : null}
        </div>
      )}

      {compareIds.length > 0 && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-brand-200 bg-brand-50/70 px-4 py-3 shadow-sm">
          <div className="flex items-center gap-2 text-xs font-medium text-brand-900">
            <GitCompareArrows size={16} className="text-brand-600" />
            <span>
              <span className="font-bold">{compareIds.length}</span> of 3 candidates selected for
              comparison
              {compareIds.length < 2 ? ' (pick at least 2)' : ''}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setCompareIds([])}>
              Clear
            </Button>
            <Button
              size="sm"
              disabled={compareIds.length < 2}
              onClick={() => navigate(`/compare?ids=${compareIds.join(',')}`)}
            >
              <GitCompareArrows size={14} />
              Compare ({compareIds.length})
            </Button>
          </div>
        </div>
      )}

      {!loading && candidates.length > 0 && view === 'grid' && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {candidates.map((c) => (
            <CandidateCard
              key={c.id}
              candidate={c}
              selectable
              selected={compareIds.includes(c.id)}
              selectDisabled={compareIds.length >= 3}
              onToggleSelect={toggleCompare}
            />
          ))}
        </div>
      )}

      {!loading && candidates.length > 0 && view === 'table' && (
        <CandidateTable
          candidates={candidates}
          selectedIds={compareIds}
          maxSelect={3}
          onToggleSelect={toggleCompare}
        />
      )}

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
