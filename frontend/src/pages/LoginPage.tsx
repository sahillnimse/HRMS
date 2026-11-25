import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  Lock,
  Mail,
  Network,
  ShieldCheck,
  Sparkles,
} from 'lucide-react'
import { useAuth } from '@/contexts/AuthContext'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'

export default function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname || '/'

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (user) {
    return <Navigate to={from} replace />
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email.trim(), password)
      navigate(from, { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background px-4 py-12">
      {/* Soft CollectUI ambient light blobs */}
      <div className="pointer-events-none absolute -left-24 -top-24 h-80 w-80 rounded-full bg-brand-200/40 blur-3xl animate-float" />
      <div
        className="pointer-events-none absolute -bottom-24 -right-24 h-80 w-80 rounded-full bg-coral-200/40 blur-3xl animate-float"
        style={{ animationDelay: '2s' }}
      />

      <div className="relative z-10 grid w-full max-w-4xl grid-cols-1 overflow-hidden rounded-3xl border border-stone-200/90 bg-white shadow-card-hover lg:grid-cols-12 animate-scale-in">
        {/* Left Editorial Light Panel */}
        <div className="hidden flex-col justify-between mesh-hero border-r border-stone-100 p-10 lg:col-span-5 lg:flex">
          <div className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500 to-teal-800 text-white shadow-glow">
              <Sparkles size={20} />
            </div>
            <div>
              <p className="font-display text-base font-bold text-slate-900">HRMS AI</p>
              <p className="text-xs font-medium text-brand-700">Talent Intelligence</p>
            </div>
          </div>

          <div className="space-y-5">
            <h2 className="font-display text-2xl font-bold leading-snug tracking-tight text-slate-900">
              Hire faster with structured CVs, deterministic scoring & blind review.
            </h2>
            <ul className="space-y-3 text-xs text-slate-600">
              {[
                {
                  icon: Network,
                  text: 'Interactive skill-to-role knowledge graphs for every candidate',
                },
                {
                  icon: CheckCircle2,
                  text: 'Hybrid semantic search & explainable 0–100 JD match breakdowns',
                },
                {
                  icon: ShieldCheck,
                  text: 'Role-based privacy controls, blind screening & audited exports',
                },
              ].map((item) => {
                const Icon = item.icon
                return (
                  <li key={item.text} className="flex items-start gap-2.5">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
                      <Icon size={12} />
                    </span>
                    <span className="leading-5">{item.text}</span>
                  </li>
                )
              })}
            </ul>
          </div>

          <p className="text-[11px] font-medium text-slate-400">
            Ocean Light Workspace · Protected by rotating HttpOnly sessions
          </p>
        </div>

        {/* Right Sign-In Form */}
        <div className="p-8 sm:p-10 lg:col-span-7">
          <div className="mb-7 lg:mb-8">
            <div className="mb-4 flex items-center gap-2.5 lg:hidden">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-teal-800 text-white shadow-glow">
                <Sparkles size={18} />
              </div>
              <span className="font-display text-base font-bold text-slate-900">HRMS AI</span>
            </div>
            <h1 className="font-display text-2xl font-bold tracking-tight text-slate-900">
              Welcome back
            </h1>
            <p className="mt-1.5 text-sm text-slate-500">
              Sign in with your workspace credentials to continue.
            </p>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {error && (
              <div className="flex items-start gap-2.5 rounded-xl border border-coral-200 bg-coral-50 px-3.5 py-3 text-xs font-medium text-coral-700 animate-fade-in">
                <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            <div className="space-y-1.5">
              <Label htmlFor="login-email">Work Email</Label>
              <div className="relative">
                <Mail
                  size={15}
                  className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <Input
                  id="login-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                  className="h-11 rounded-xl pl-10"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="login-password">Password</Label>
              <div className="relative">
                <Lock
                  size={15}
                  className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                />
                <Input
                  id="login-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="h-11 rounded-xl pl-10 pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 transition hover:bg-stone-100 hover:text-slate-700"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <Button type="submit" size="lg" loading={submitting} className="h-11 w-full shadow-glow">
              Sign In to Workspace
              {!submitting && <ArrowRight size={16} />}
            </Button>
          </form>

          <p className="mt-6 text-center text-xs text-slate-400">
            Protected workspace · Contact an administrator for account access
          </p>
        </div>
      </div>
    </div>
  )
}
