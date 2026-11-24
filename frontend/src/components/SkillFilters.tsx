import { useState } from 'react'
import { Search, X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface SkillFiltersProps {
  availableSkills: string[]
  selectedSkills: string[]
  onToggleSkill: (skill: string) => void
  onClearSkills: () => void
}

export function SkillFilters({
  availableSkills,
  selectedSkills,
  onToggleSkill,
  onClearSkills,
}: SkillFiltersProps) {
  const [query, setQuery] = useState('')

  const filtered = availableSkills.filter((s) =>
    s.toLowerCase().includes(query.trim().toLowerCase()),
  )

  return (
    <div className="space-y-3 border-t border-slate-100 pt-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="relative flex-1 min-w-[200px] max-w-xs">
          <Search
            size={14}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            type="text"
            placeholder="Filter skill tags…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-8 w-full rounded-lg border border-slate-200 bg-slate-50/60 pl-8 pr-3 text-xs text-slate-800 outline-none transition focus:border-brand-400 focus:bg-white focus:ring-2 focus:ring-brand-100"
          />
        </div>
        {selectedSkills.length > 0 && (
          <button
            type="button"
            onClick={onClearSkills}
            className="inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:text-brand-700"
          >
            <X size={13} />
            Clear {selectedSkills.length} selected skill{selectedSkills.length === 1 ? '' : 's'}
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {filtered.map((skill) => {
          const active = selectedSkills.includes(skill)
          return (
            <button
              key={skill}
              type="button"
              onClick={() => onToggleSkill(skill)}
              className={cn(
                'rounded-full border px-2.5 py-1 text-xs font-medium transition',
                active
                  ? 'border-brand-600 bg-brand-600 text-white shadow-sm'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-brand-300 hover:bg-brand-50/60 hover:text-brand-700',
              )}
            >
              {skill}
            </button>
          )
        })}
        {filtered.length === 0 && (
          <p className="text-xs italic text-slate-400">No skills match “{query}”</p>
        )}
      </div>
    </div>
  )
}
