import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatDate(dateStr?: string | null): string {
  if (!dateStr) return '-'
  if (dateStr.toLowerCase() === 'present') return 'Present'
  return dateStr
}

export function truncate(text: string, len: number): string {
  if (!text) return ''
  return text.length > len ? text.slice(0, len).trim() + '…' : text
}

export function joinSkills(skills: string[]): string {
  return skills.filter(Boolean).join(', ')
}

export function formatYears(years: number | null | undefined): string {
  const value = Number(years) || 0
  const rounded = Math.round(value * 10) / 10
  return `${rounded} ${rounded === 1 ? 'yr' : 'yrs'}`
}

export function formatLongDate(iso?: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

export function formatRelativeDate(iso?: string | null): string {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  const days = Math.floor((Date.now() - date.getTime()) / 86_400_000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 7) return `${days} days ago`
  if (days < 30) return `${Math.floor(days / 7)} wk${days < 14 ? '' : 's'} ago`
  return formatLongDate(iso)
}
