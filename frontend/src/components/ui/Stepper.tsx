import { Check } from 'lucide-react'
import { cn } from '@/lib/utils'

const STEPS = ['Upload resume', 'AI parsing', 'Review & save']

export function Stepper({ current }: { current: number }) {
  return (
    <ol className="flex flex-wrap items-center gap-2 sm:gap-3">
      {STEPS.map((label, index) => {
        const state = index < current ? 'done' : index === current ? 'active' : 'todo'
        return (
          <li key={label} className="flex items-center gap-2 sm:gap-3">
            <div className="flex items-center gap-2">
              <span
                className={cn(
                  'flex h-7 w-7 items-center justify-center rounded-full text-xs font-semibold transition',
                  state === 'done' && 'bg-brand-600 text-white',
                  state === 'active' && 'bg-brand-50 text-brand-700 ring-2 ring-brand-500',
                  state === 'todo' && 'bg-slate-100 text-slate-500',
                )}
              >
                {state === 'done' ? <Check size={14} /> : index + 1}
              </span>
              <span
                className={cn(
                  'hidden text-sm font-medium sm:inline',
                  state === 'todo' ? 'text-slate-400' : 'text-slate-800',
                )}
              >
                {label}
              </span>
            </div>
            {index < STEPS.length - 1 && (
              <span className={cn('h-px w-6 sm:w-10', index < current ? 'bg-brand-400' : 'bg-slate-200')} />
            )}
          </li>
        )
      })}
    </ol>
  )
}
