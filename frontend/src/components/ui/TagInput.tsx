import { useRef, useState } from 'react'
import { X } from 'lucide-react'
import { cn } from '@/lib/utils'

interface TagTone {
  bg: string
  text: string
}

interface TagInputProps {
  value: string[]
  onChange: (next: string[]) => void
  placeholder?: string
  tone?: TagTone
  className?: string
}

export function TagInput({ value, onChange, placeholder = 'Type and press Enter', tone, className }: TagInputProps) {
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const add = (raw: string) => {
    const parts = raw.split(',').map((s) => s.trim()).filter(Boolean)
    if (parts.length === 0) {
      setDraft('')
      return
    }
    const existing = new Set(value.map((v) => v.toLowerCase()))
    const next = [...value]
    for (const part of parts) {
      if (!existing.has(part.toLowerCase())) {
        next.push(part)
        existing.add(part.toLowerCase())
      }
    }
    onChange(next)
    setDraft('')
  }

  return (
    <div
      onClick={() => inputRef.current?.focus()}
      className={cn(
        'flex min-h-[44px] cursor-text flex-wrap items-center gap-1.5 rounded-lg border border-input bg-white px-2 py-1.5 shadow-sm transition focus-within:border-brand-400 focus-within:ring-4 focus-within:ring-brand-100',
        className,
      )}
    >
      {value.map((tag, index) => (
        <span
          key={`${tag}-${index}`}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium"
          style={{ backgroundColor: tone?.bg ?? '#f1f5f9', color: tone?.text ?? '#334155' }}
        >
          {tag}
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onChange(value.filter((_, i) => i !== index))
            }}
            className="rounded opacity-60 transition hover:opacity-100"
            aria-label={`Remove ${tag}`}
          >
            <X size={12} />
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault()
            add(draft)
          } else if (e.key === 'Backspace' && !draft && value.length > 0) {
            onChange(value.slice(0, -1))
          }
        }}
        onBlur={() => {
          if (draft.trim()) add(draft)
        }}
        placeholder={value.length ? 'Add more…' : placeholder}
        className="min-w-[120px] flex-1 border-0 bg-transparent px-1 py-1 text-sm text-slate-800 outline-none placeholder:text-slate-400"
      />
    </div>
  )
}
