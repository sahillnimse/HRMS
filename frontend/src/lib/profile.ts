import type {
  CandidateProfileData,
  CandidateUpdate,
  ParsedResumeData,
  WorkExperienceItem,
} from '@/types'

const AVATAR_GRADIENTS = [
  'from-indigo-500 to-violet-500',
  'from-sky-500 to-indigo-500',
  'from-emerald-500 to-teal-500',
  'from-rose-500 to-pink-500',
  'from-amber-500 to-orange-500',
  'from-violet-500 to-fuchsia-500',
  'from-cyan-500 to-blue-500',
]

export function getInitials(name: string): string {
  const parts = (name || '').trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function getAvatarGradient(name: string): string {
  let hash = 0
  for (const ch of name || '') hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return AVATAR_GRADIENTS[hash % AVATAR_GRADIENTS.length]
}

export function isCurrentRole(endDate: string | null | undefined): boolean {
  const value = (endDate ?? '').trim().toLowerCase()
  return value === 'present' || value === 'current' || value === 'now'
}

export function getCurrentRole(
  work: WorkExperienceItem[],
): { title: string; company: string } | null {
  if (!work?.length) return null
  const current = work.find((w) => isCurrentRole(w.end_date)) ?? work[0]
  return { title: current.job_title, company: current.company }
}

export function getSeniority(years: number): string {
  const y = Number(years) || 0
  if (y < 2) return 'Entry level'
  if (y < 5) return 'Mid level'
  if (y < 10) return 'Senior'
  return 'Lead / Principal'
}

export interface Completeness {
  score: number
  missing: string[]
}

export function computeCompleteness(p: CandidateProfileData): Completeness {
  const checks: [string, boolean, number][] = [
    ['Full name', !!p.full_name?.trim(), 10],
    ['Email', !!p.email, 10],
    ['Phone', !!p.phone, 8],
    ['Location', !!p.city, 5],
    ['Online profile', !!(p.linkedin_url || p.github_url || p.portfolio_url), 7],
    ['Summary', (p.profile_summary ?? '').trim().length >= 40, 12],
    ['Primary domain', !!p.primary_domain?.trim(), 8],
    ['Work experience', p.work_experience.length > 0, 15],
    ['Education', p.education.length > 0, 10],
    ['3+ technical skills', p.technical_skills.length >= 3, 10],
    ['Languages', p.languages.length > 0, 3],
    ['Certifications', p.certifications.length > 0, 2],
  ]
  let score = 0
  const missing: string[] = []
  for (const [label, ok, weight] of checks) {
    if (ok) score += weight
    else missing.push(label)
  }
  return { score, missing }
}

const toStringList = (value: unknown): string[] =>
  Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []

type ProfileSource = Partial<CandidateProfileData> & {
  raw_parsed_data?: Record<string, unknown> | null
}

/** Coerce any parsed / saved candidate payload into a complete, safe form object. */
export function normalizeProfile(src: ProfileSource): ParsedResumeData {
  return {
    full_name: src.full_name ?? '',
    email: src.email ?? null,
    phone: src.phone ?? null,
    city: src.city ?? null,
    linkedin_url: src.linkedin_url ?? null,
    github_url: src.github_url ?? null,
    portfolio_url: src.portfolio_url ?? null,
    profile_summary: src.profile_summary ?? '',
    years_experience: Number(src.years_experience) || 0,
    primary_domain: src.primary_domain ?? '',
    work_experience: Array.isArray(src.work_experience)
      ? src.work_experience.map((w) => ({
          company: w?.company ?? '',
          job_title: w?.job_title ?? '',
          start_date: w?.start_date ?? null,
          end_date: w?.end_date ?? null,
          bullets: toStringList(w?.bullets),
        }))
      : [],
    education: Array.isArray(src.education)
      ? src.education.map((e) => ({
          degree: e?.degree ?? '',
          institution: e?.institution ?? '',
          graduation_year: typeof e?.graduation_year === 'number' ? e.graduation_year : null,
        }))
      : [],
    technical_skills: toStringList(src.technical_skills),
    tools: toStringList(src.tools),
    soft_skills: toStringList(src.soft_skills),
    hobbies_interests: toStringList(src.hobbies_interests),
    languages: toStringList(src.languages),
    certifications: toStringList(src.certifications),
    notice_period_days:
      typeof src.notice_period_days === 'number' ? src.notice_period_days : null,
    current_ctc: typeof src.current_ctc === 'number' ? src.current_ctc : null,
    expected_ctc: typeof src.expected_ctc === 'number' ? src.expected_ctc : null,
    ctc_currency: src.ctc_currency ?? null,
    preferred_locations: toStringList(src.preferred_locations),
    open_to_relocate:
      typeof src.open_to_relocate === 'boolean' ? src.open_to_relocate : null,
    raw_parsed_data: src.raw_parsed_data ?? {},
  }
}

export type FormErrors = Partial<Record<'full_name' | 'primary_domain' | 'profile_summary' | 'email', string>>

export function validateProfile(p: ParsedResumeData): FormErrors {
  const errors: FormErrors = {}
  if (!p.full_name.trim()) errors.full_name = 'Full name is required'
  if (!p.primary_domain.trim()) errors.primary_domain = 'Primary domain is required'
  if (!p.profile_summary.trim()) errors.profile_summary = 'A short profile summary is required'
  if (p.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(p.email.trim())) {
    errors.email = 'Enter a valid email address'
  }
  return errors
}

/** Clean form data into the API payload (trim, nullify blanks, drop empty rows). */
export function toCandidatePayload(f: ParsedResumeData): CandidateUpdate {
  const clean = (v: string | null | undefined) => {
    const t = (v ?? '').trim()
    return t ? t : null
  }
  const list = (v: string[]) => v.map((s) => s.trim()).filter(Boolean)

  return {
    full_name: f.full_name.trim(),
    email: clean(f.email),
    phone: clean(f.phone),
    city: clean(f.city),
    linkedin_url: clean(f.linkedin_url),
    github_url: clean(f.github_url),
    portfolio_url: clean(f.portfolio_url),
    profile_summary: f.profile_summary.trim(),
    years_experience: Math.max(0, Number(f.years_experience) || 0),
    primary_domain: f.primary_domain.trim(),
    work_experience: f.work_experience
      .filter((w) => w.company.trim() || w.job_title.trim())
      .map((w) => ({
        company: w.company.trim(),
        job_title: w.job_title.trim(),
        start_date: clean(w.start_date),
        end_date: clean(w.end_date),
        bullets: list(w.bullets),
      })),
    education: f.education
      .filter((e) => e.degree.trim() || e.institution.trim())
      .map((e) => ({
        degree: e.degree.trim(),
        institution: e.institution.trim(),
        graduation_year: e.graduation_year,
      })),
    technical_skills: list(f.technical_skills),
    tools: list(f.tools),
    soft_skills: list(f.soft_skills),
    hobbies_interests: list(f.hobbies_interests),
    languages: list(f.languages),
    certifications: list(f.certifications),
    notice_period_days:
      typeof f.notice_period_days === 'number' && !Number.isNaN(f.notice_period_days)
        ? Math.max(0, Math.round(f.notice_period_days))
        : null,
    current_ctc:
      typeof f.current_ctc === 'number' && !Number.isNaN(f.current_ctc)
        ? Math.max(0, f.current_ctc)
        : null,
    expected_ctc:
      typeof f.expected_ctc === 'number' && !Number.isNaN(f.expected_ctc)
        ? Math.max(0, f.expected_ctc)
        : null,
    ctc_currency: clean(f.ctc_currency)?.toUpperCase() ?? null,
    preferred_locations: list(f.preferred_locations ?? []),
    open_to_relocate: typeof f.open_to_relocate === 'boolean' ? f.open_to_relocate : null,
    raw_parsed_data: f.raw_parsed_data,
  }
}

export function formatCtc(amount: number | null | undefined, currency?: string | null): string {
  if (amount == null || Number.isNaN(amount)) return '—'
  const code = (currency || 'INR').toUpperCase()
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: code,
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    return `${code} ${amount.toLocaleString()}`
  }
}

export function getStoredFilename(raw: Record<string, unknown> | null | undefined): string | null {
  const value = raw?._stored_filename
  return typeof value === 'string' && value ? value : null
}

export function getSourceFilename(raw: Record<string, unknown> | null | undefined): string | null {
  const value = raw?._source_filename
  return typeof value === 'string' && value ? value : null
}

export function ensureProtocol(url: string): string {
  return /^https?:\/\//i.test(url) ? url : `https://${url}`
}

export function prettyUrl(url: string): string {
  return url.replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/\/$/, '')
}
