import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { ArrowRight, Brain, LayoutDashboard, Sparkles, Upload } from 'lucide-react'
import { Avatar } from '@/components/ui/Avatar'
import { cn } from '@/lib/utils'

interface NavEntry {
  to: string
  label: string
  icon: LucideIcon
  match: (path: string) => boolean
}

const NAV: NavEntry[] = [
  {
    to: '/',
    label: 'Dashboard',
    icon: LayoutDashboard,
    match: (p) => p === '/' || p.startsWith('/candidates'),
  },
  {
    to: '/upload',
    label: 'Upload Resume',
    icon: Upload,
    match: (p) => p.startsWith('/upload') || p.startsWith('/review'),
  },
]

function BrandMark() {
  return (
    <Link to="/" className="flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-600 text-white shadow-glow">
        <Sparkles size={18} />
      </div>
      <div className="leading-tight">
        <p className="text-[15px] font-semibold text-slate-900">HRMS AI</p>
        <p className="text-[11px] font-medium text-slate-500">Talent Intelligence</p>
      </div>
    </Link>
  )
}

function Sidebar() {
  const { pathname } = useLocation()
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200/80 bg-white lg:flex">
      <div className="flex h-16 items-center border-b border-slate-100 px-6">
        <BrandMark />
      </div>

      <nav className="flex-1 px-3 py-6">
        <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">Workspace</p>
        <div className="space-y-1">
          {NAV.map((item) => {
            const active = item.match(pathname)
            const Icon = item.icon
            return (
              <Link
                key={item.to}
                to={item.to}
                className={cn(
                  'group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition',
                  active ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900',
                )}
              >
                {active && <span className="absolute inset-y-2 left-0 w-1 rounded-r-full bg-brand-600" />}
                <Icon size={18} className={active ? 'text-brand-600' : 'text-slate-400 group-hover:text-slate-600'} />
                {item.label}
              </Link>
            )
          })}
        </div>
      </nav>

      <div className="mx-3 mb-3 rounded-xl border border-brand-100 bg-gradient-to-br from-brand-50 to-violet-50 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold text-brand-900">
          <Brain size={16} className="text-brand-600" />
          AI resume parsing
        </div>
        <p className="mt-1.5 text-xs leading-5 text-slate-600">
          Gemini structures every CV into a profile and network graph. HR verifies before saving.
        </p>
        <Link
          to="/upload"
          className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-brand-700 hover:text-brand-800"
        >
          Parse a resume <ArrowRight size={13} />
        </Link>
      </div>

      <div className="flex items-center gap-3 border-t border-slate-100 p-4">
        <Avatar name="HR Team" size="sm" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-slate-900">HR Workspace</p>
          <p className="truncate text-xs text-slate-500">Recruitment team</p>
        </div>
      </div>
    </aside>
  )
}

function MobileNav() {
  const { pathname } = useLocation()
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-slate-200/80 bg-white/90 px-4 backdrop-blur lg:hidden">
      <BrandMark />
      <nav className="flex items-center gap-1">
        {NAV.map((item) => {
          const Icon = item.icon
          const active = item.match(pathname)
          return (
            <Link
              key={item.to}
              to={item.to}
              aria-label={item.label}
              className={cn(
                'flex h-9 w-9 items-center justify-center rounded-lg transition',
                active ? 'bg-brand-50 text-brand-700' : 'text-slate-500 hover:bg-slate-100',
              )}
            >
              <Icon size={18} />
            </Link>
          )
        })}
      </nav>
    </header>
  )
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <MobileNav />
      <div className="lg:pl-64">
        <main className="mx-auto w-full max-w-[1400px] px-4 py-6 sm:px-6 lg:px-10 lg:py-8">{children}</main>
      </div>
    </div>
  )
}
