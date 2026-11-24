import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface TabItem<T extends string> {
  value: T
  label: string
  icon?: LucideIcon
  badge?: string | number
}

interface TabsProps<T extends string> {
  value: T
  onChange: (value: T) => void
  items: TabItem<T>[]
  className?: string
}

export function Tabs<T extends string>({ value, onChange, items, className }: TabsProps<T>) {
  return (
    <div
      role="tablist"
      className={cn('inline-flex flex-wrap gap-1 rounded-xl border border-slate-200 bg-slate-100/70 p-1', className)}
    >
      {items.map((item) => {
        const Icon = item.icon
        const active = item.value === value
        return (
          <button
            key={item.value}
            role="tab"
            type="button"
            aria-selected={active}
            onClick={() => onChange(item.value)}
            className={cn(
              'inline-flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition',
              active ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800',
            )}
          >
            {Icon && <Icon size={16} className={active ? 'text-brand-600' : undefined} />}
            {item.label}
            {item.badge != null && (
              <span className="rounded-full bg-slate-200/80 px-1.5 text-[11px] font-semibold text-slate-600">
                {item.badge}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
