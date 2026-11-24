import type { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'

interface PageHeaderProps {
  eyebrow?: ReactNode
  title: string
  description?: ReactNode
  actions?: ReactNode
  onBack?: () => void
  backLabel?: string
}

export function PageHeader({ eyebrow, title, description, actions, onBack, backLabel = 'Back' }: PageHeaderProps) {
  return (
    <div className="flex flex-col gap-4 animate-fade-in md:flex-row md:items-end md:justify-between">
      <div className="min-w-0 space-y-2">
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-slate-500 transition hover:text-slate-900"
          >
            <ArrowLeft size={16} />
            {backLabel}
          </button>
        )}
        {eyebrow && (
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand-600">{eyebrow}</p>
        )}
        <h1 className="text-2xl font-semibold tracking-tight text-slate-900 sm:text-[28px]">{title}</h1>
        {description && <p className="max-w-2xl text-sm leading-6 text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}
