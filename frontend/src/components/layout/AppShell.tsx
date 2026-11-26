import { useEffect, useState, type ReactNode } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import {
  ArrowRight,
  BarChart3,
  Brain,
  Briefcase,
  Calendar,
  ChevronLeft,
  Eye,
  EyeOff,
  LayoutDashboard,
  LogOut,
  Shield,
  Sparkles,
  Upload,
  Users,
} from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/lib/utils'

const SIDEBAR_STORAGE_KEY = 'hrms_sidebar_collapsed'

interface NavEntry {
  to: string
  label: string
  icon: LucideIcon
  writeOnly?: boolean
  adminOnly?: boolean
  match: (path: string) => boolean
}

const NAV: NavEntry[] = [
  {
    to: '/',
    label: 'Dashboard',
    icon: LayoutDashboard,
    match: (p) => p === '/',
  },
  {
    to: '/candidates',
    label: 'Candidates',
    icon: Users,
    match: (p) => p.startsWith('/candidates') || p.startsWith('/compare'),
  },
  {
    to: '/jobs',
    label: 'Jobs',
    icon: Briefcase,
    match: (p) => p.startsWith('/jobs'),
  },
  {
    to: '/interviews',
    label: 'Interviews',
    icon: Calendar,
    match: (p) => p.startsWith('/interviews'),
  },
  {
    to: '/analytics',
    label: 'Analytics',
    icon: BarChart3,
    match: (p) => p.startsWith('/analytics'),
  },
  {
    to: '/upload',
    label: 'Upload Resume',
    icon: Upload,
    writeOnly: true,
    match: (p) => p.startsWith('/upload') || p.startsWith('/review'),
  },
  {
    to: '/privacy',
    label: 'Privacy & Retention',
    icon: Shield,
    adminOnly: true,
    match: (p) => p.startsWith('/privacy'),
  },
]

function BrandMark({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <Link
      to="/"
      className={cn(
        'group flex items-center gap-3 overflow-hidden transition-all duration-300',
        collapsed && 'justify-center',
      )}
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 via-brand-600 to-teal-800 text-white shadow-glow transition-transform duration-300 group-hover:scale-105">
        <Sparkles size={19} className="transition-transform duration-300 group-hover:rotate-12" />
      </div>
      {!collapsed && (
        <div className="min-w-0 leading-tight animate-slide-in-left">
          <p className="truncate font-display text-[15px] font-bold tracking-tight text-slate-900">
            HRMS AI
          </p>
          <p className="truncate text-[11px] font-medium text-brand-700/80">Talent Intelligence</p>
        </div>
      )}
    </Link>
  )
}

function Sidebar({
  collapsed,
  onToggleCollapse,
}: {
  collapsed: boolean
  onToggleCollapse: () => void
}) {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { user, canWrite, isAdmin, logout } = useAuth()
  const { blindMode, toggleBlindMode } = useBlindMode()

  const visibleNav = NAV.filter(
    (item) => (!item.writeOnly || canWrite) && (!item.adminOnly || isAdmin),
  )

  const handleLogout = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <aside
      className={cn(
        'fixed inset-y-0 left-0 z-30 hidden flex-col border-r border-stone-200/80 bg-white/95 backdrop-blur-md transition-[width] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] lg:flex',
        collapsed ? 'w-[82px]' : 'w-[264px]',
      )}
    >
      {/* Floating CollectUI-style Collapse / Expand Toggle Button */}
      <button
        type="button"
        onClick={onToggleCollapse}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        title={collapsed ? 'Expand sidebar (Ctrl+B)' : 'Collapse sidebar (Ctrl+B)'}
        className="group absolute -right-3.5 top-6 z-40 flex h-7 w-7 items-center justify-center rounded-full border border-stone-200 bg-white text-slate-500 shadow-float transition-all duration-200 hover:scale-105 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand-100"
      >
        <ChevronLeft
          size={15}
          className={cn(
            'transition-transform duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]',
            collapsed && 'rotate-180',
          )}
        />
      </button>

      {/* Top Brand Header */}
      <div
        className={cn(
          'flex h-[70px] items-center border-b border-stone-100 transition-all duration-300',
          collapsed ? 'justify-center px-3' : 'px-5',
        )}
      >
        <BrandMark collapsed={collapsed} />
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 overflow-y-auto overflow-x-visible px-3 py-5">
        {!collapsed ? (
          <p className="px-3 pb-2.5 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
            Workspace
          </p>
        ) : (
          <div className="mx-auto mb-3 h-px w-7 bg-stone-200/80" />
        )}

        <div className="space-y-1.5">
          {visibleNav.map((item) => {
            const active = item.match(pathname)
            const Icon = item.icon
            return (
              <Link
                key={item.to}
                to={item.to}
                title={collapsed ? item.label : undefined}
                className={cn(
                  'group relative flex items-center rounded-xl text-sm font-medium transition-all duration-200',
                  collapsed ? 'justify-center px-2 py-2.5' : 'gap-3 px-3.5 py-2.5',
                  active
                    ? 'bg-gradient-to-r from-brand-50 via-brand-50/80 to-transparent text-brand-800 shadow-[inset_0_0_0_1px_rgba(15,157,138,0.16)]'
                    : 'text-slate-600 hover:bg-stone-100/75 hover:text-slate-900',
                )}
              >
                {active && (
                  <span className="absolute inset-y-2 left-0 w-1 rounded-r-full bg-brand-500 transition-all" />
                )}
                <Icon
                  size={18}
                  className={cn(
                    'shrink-0 transition-transform duration-200 group-hover:scale-110',
                    active ? 'text-brand-600' : 'text-slate-400 group-hover:text-brand-600',
                  )}
                />
                {!collapsed && <span className="truncate">{item.label}</span>}

                {/* Floating tooltip when collapsed */}
                {collapsed && (
                  <span className="pointer-events-none absolute left-full ml-3 z-50 whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs font-semibold text-white opacity-0 shadow-lg transition-all duration-150 -translate-x-1 group-hover:translate-x-0 group-hover:opacity-100">
                    {item.label}
                  </span>
                )}
              </Link>
            )
          })}
        </div>

        {/* Blind Screening Mode Switch */}
        <div className={cn('mt-6', collapsed ? 'px-0' : 'px-0.5')}>
          <button
            type="button"
            onClick={toggleBlindMode}
            title="Blind Screening: hide candidate names, contacts, avatars, and colleges in UI & exports"
            className={cn(
              'group relative flex w-full items-center rounded-xl border text-xs font-semibold transition-all duration-200',
              collapsed ? 'justify-center p-2.5' : 'justify-between gap-2 px-3 py-2.5 text-left',
              blindMode
                ? 'border-amber-300 bg-amber-50/90 text-amber-900 shadow-sm'
                : 'border-stone-200/80 bg-stone-50/70 text-slate-600 hover:border-brand-200 hover:bg-brand-50/40 hover:text-slate-900',
            )}
          >
            <span className="inline-flex items-center gap-2">
              {blindMode ? (
                <EyeOff size={16} className="shrink-0 text-amber-600" />
              ) : (
                <Eye size={16} className="shrink-0 text-slate-400 group-hover:text-brand-600" />
              )}
              {!collapsed && <span>Blind Screening</span>}
            </span>
            {!collapsed && (
              <span
                className={cn(
                  'rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide transition-colors',
                  blindMode ? 'bg-amber-600 text-white' : 'bg-stone-200/90 text-slate-600',
                )}
              >
                {blindMode ? 'ON' : 'OFF'}
              </span>
            )}
            {collapsed && (
              <span className="pointer-events-none absolute left-full ml-3 z-50 whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs font-semibold text-white opacity-0 shadow-lg transition-all duration-150 -translate-x-1 group-hover:translate-x-0 group-hover:opacity-100">
                Blind Screening: {blindMode ? 'ON' : 'OFF'}
              </span>
            )}
          </button>
        </div>
      </nav>

      {/* AI Parsing Promo Card (hidden in compact rail mode) */}
      {canWrite && !collapsed && (
        <div className="mx-3 mb-3 overflow-hidden rounded-2xl border border-brand-200/70 bg-gradient-to-br from-brand-50 via-white to-coral-50/70 p-4 shadow-sm animate-fade-in">
          <div className="flex items-center gap-2 text-sm font-bold text-slate-900">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand-600 text-white shadow-sm">
              <Brain size={14} />
            </span>
            AI Resume Studio
          </div>
          <p className="mt-2 text-xs leading-5 text-slate-600">
            Single or bulk CV upload, automatic OCR for scanned PDFs, and instant skill graphs.
          </p>
          <Link
            to="/upload"
            className="group mt-3 inline-flex items-center gap-1.5 text-xs font-bold text-brand-700 hover:text-brand-800"
          >
            Parse resumes
            <ArrowRight
              size={13}
              className="transition-transform duration-200 group-hover:translate-x-1"
            />
          </Link>
        </div>
      )}

      {/* User Footer */}
      <div
        className={cn(
          'border-t border-stone-100 p-3.5 transition-all',
          collapsed
            ? 'flex flex-col items-center gap-2.5'
            : 'flex items-center justify-between gap-2',
        )}
      >
        <div
          className={cn('flex min-w-0 items-center gap-2.5', collapsed && 'justify-center')}
          title={collapsed ? `${user?.full_name || user?.email || 'User'} (${user?.role ?? 'user'})` : undefined}
        >
          <Avatar name={user?.full_name || user?.email || 'User'} size="sm" />
          {!collapsed && (
            <div className="min-w-0">
              <p className="truncate text-xs font-bold text-slate-900">
                {user?.full_name || user?.email || 'User'}
              </p>
              <div className="mt-0.5 flex items-center gap-1.5">
                <Badge variant="brand" className="px-1.5 py-0 text-[10px] capitalize">
                  {user?.role ?? 'user'}
                </Badge>
              </div>
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={handleLogout}
          title="Sign out"
          aria-label="Sign out"
          className="rounded-xl p-2 text-slate-400 transition-all duration-200 hover:bg-coral-50 hover:text-coral-600"
        >
          <LogOut size={16} />
        </button>
      </div>
    </aside>
  )
}

function MobileNav() {
  const { pathname } = useLocation()
  const navigate = useNavigate()
  const { canWrite, isAdmin, logout } = useAuth()
  const { blindMode, toggleBlindMode } = useBlindMode()
  const visibleNav = NAV.filter(
    (item) => (!item.writeOnly || canWrite) && (!item.adminOnly || isAdmin),
  )

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-stone-200/80 bg-white/90 px-4 backdrop-blur-md lg:hidden">
      <BrandMark />
      <nav className="flex items-center gap-1">
        {visibleNav.map((item) => {
          const Icon = item.icon
          const active = item.match(pathname)
          return (
            <Link
              key={item.to}
              to={item.to}
              aria-label={item.label}
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-xl transition',
                active ? 'bg-brand-50 text-brand-700' : 'text-slate-500 hover:bg-stone-100',
              )}
            >
              <Icon size={18} />
            </Link>
          )
        })}
        <button
          type="button"
          onClick={toggleBlindMode}
          aria-label="Toggle Blind Screening Mode"
          title="Toggle Blind Screening Mode"
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-xl transition',
            blindMode ? 'bg-amber-100 text-amber-800' : 'text-slate-500 hover:bg-stone-100',
          )}
        >
          {blindMode ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
        <button
          type="button"
          onClick={async () => {
            await logout()
            navigate('/login', { replace: true })
          }}
          aria-label="Sign out"
          className="flex h-9 w-9 items-center justify-center rounded-xl text-slate-500 transition hover:bg-coral-50 hover:text-coral-600"
        >
          <LogOut size={17} />
        </button>
      </nav>
    </header>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  const { blindMode, toggleBlindMode } = useBlindMode()
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  const toggleCollapse = () => {
    setCollapsed((prev) => {
      const next = !prev
      try {
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? 'true' : 'false')
      } catch {
        // Ignore storage errors
      }
      return next
    })
  }

  // Keyboard shortcut Ctrl+B / Cmd+B to toggle sidebar
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        const tag = (e.target as HTMLElement | null)?.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
        e.preventDefault()
        setCollapsed((prev) => {
          const next = !prev
          try {
            window.localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? 'true' : 'false')
          } catch {
            // Ignore
          }
          return next
        })
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <div className="min-h-screen bg-background">
      <Sidebar collapsed={collapsed} onToggleCollapse={toggleCollapse} />
      <MobileNav />
      <div
        className={cn(
          'transition-[padding-left] duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]',
          collapsed ? 'lg:pl-[82px]' : 'lg:pl-[264px]',
        )}
      >
        {blindMode && (
          <div className="border-b border-amber-200 bg-amber-50/90 px-4 py-2 text-xs text-amber-900 backdrop-blur sm:px-6 lg:px-10 animate-fade-in">
            <div className="mx-auto flex max-w-[1440px] items-center justify-between gap-3">
              <span className="inline-flex items-center gap-2 font-medium">
                <EyeOff size={14} className="shrink-0 text-amber-600" />
                Blind Screening Mode is active — candidate names, emails, phones, social links, and
                institutions are masked across views and exports.
              </span>
              <button
                type="button"
                onClick={toggleBlindMode}
                className="shrink-0 rounded-lg border border-amber-300 bg-white px-2.5 py-0.5 text-[11px] font-semibold text-amber-900 transition hover:bg-amber-100"
              >
                Turn Off
              </button>
            </div>
          </div>
        )}
        <main className="mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 lg:px-10 lg:py-8">
          {children}
        </main>
      </div>
    </div>
  )
}
