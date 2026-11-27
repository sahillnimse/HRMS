import { useState } from 'react'
import {
  Award,
  Briefcase,
  Check,
  Code2,
  Copy,
  ExternalLink,
  EyeOff,
  FileText,
  FolderGit2,
  Github,
  Globe,
  GraduationCap,
  Heart,
  Languages,
  Linkedin,
  Mail,
  MapPin,
  Phone,
  Sparkles,
  Users,
  Wrench,
} from 'lucide-react'
import type { CandidateProfileData, SkillEvidenceItem } from '@/types'
import { fetchResumeBlob } from '@/lib/api'
import { useAuth } from '@/contexts/AuthContext'
import { useBlindMode } from '@/contexts/BlindModeContext'
import { cn, formatDate, formatLongDate, formatYears } from '@/lib/utils'
import {
  computeCompleteness,
  ensureProtocol,
  formatCtc,
  formatEmploymentType,
  getCurrentRole,
  getSeniority,
  getSourceFilename,
  getStoredFilename,
  isCurrentRole,
  prettyUrl,
} from '@/lib/profile'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { CandidateNetworkGraph } from '@/components/CandidateNetworkGraph'
import { ResumePreview } from '@/components/ResumePreview'

interface CandidateProfileOverviewProps {
  profile: CandidateProfileData
  rawParsedData?: Record<string, unknown> | null
  resumeFileId?: string | null
  createdAt?: string | null
  showGraph?: boolean
  headerActions?: React.ReactNode
  skillEvidence?: SkillEvidenceItem[]
}

const EVIDENCE_SOURCE_LABELS: Record<string, string> = {
  experience: 'Experience',
  projects: 'Projects',
  certification: 'Certification',
  education: 'Education',
}

function CompletenessRing({ score, missing }: { score: number; missing: string[] }) {
  const radius = 26
  const circ = 2 * Math.PI * radius
  const offset = circ * (1 - score / 100)
  const color = score >= 80 ? '#0d8274' : score >= 55 ? '#0f9d8a' : '#f25c43'

  return (
    <div
      className="flex items-center gap-3 rounded-xl border border-slate-200/80 bg-white/90 px-3.5 py-2.5 shadow-sm backdrop-blur"
      title={missing.length ? `Missing: ${missing.join(', ')}` : 'All key profile fields captured'}
    >
      <div className="relative flex h-14 w-14 shrink-0 items-center justify-center">
        <svg className="-rotate-90" width={60} height={60} viewBox="0 0 60 60">
          <circle cx={30} cy={30} r={radius} fill="none" stroke="#e2e8f0" strokeWidth={5} />
          <circle
            cx={30}
            cy={30}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={5}
            strokeDasharray={circ}
            strokeDashoffset={offset}
            strokeLinecap="round"
          />
        </svg>
        <span className="absolute text-xs font-bold text-slate-900">{score}%</span>
      </div>
      <div className="min-w-0">
        <p className="text-xs font-semibold text-slate-900">Profile Score</p>
        <p className="text-[11px] text-slate-500">
          {missing.length === 0
            ? 'Complete dossier'
            : `${missing.length} optional field${missing.length === 1 ? '' : 's'} empty`}
        </p>
      </div>
    </div>
  )
}

function detectRoleSkills(bullets: string[], title: string, skills: string[]): string[] {
  const text = `${title} ${bullets.join(' ')}`.toLowerCase()
  return skills
    .filter((s) => s.trim().length >= 2 && text.includes(s.trim().toLowerCase()))
    .slice(0, 6)
}

export function CandidateProfileOverview({
  profile,
  rawParsedData,
  resumeFileId,
  createdAt,
  showGraph = true,
  headerActions,
  skillEvidence,
}: CandidateProfileOverviewProps) {
  const [copiedEmail, setCopiedEmail] = useState(false)
  const [openingCv, setOpeningCv] = useState(false)
  const { canWrite } = useAuth()
  const { blindMode } = useBlindMode()

  const evidenceMap = new Map<string, string[]>()
  for (const item of skillEvidence ?? []) {
    evidenceMap.set(item.skill.toLowerCase(), item.sources)
  }
  const hasEvidenceData = (skillEvidence?.length ?? 0) > 0

  const currentRole = getCurrentRole(profile.work_experience)
  const seniority = getSeniority(profile.years_experience)
  const completeness = computeCompleteness(profile)
  const allCapabilities = [...profile.technical_skills, ...profile.tools]
  const storedFilename = getStoredFilename(rawParsedData)
  const sourceFilename = getSourceFilename(rawParsedData)

  const openSavedResume = async () => {
    if (!resumeFileId) return
    try {
      setOpeningCv(true)
      const blob = await fetchResumeBlob(resumeFileId, false)
      const url = URL.createObjectURL(blob)
      window.open(url, '_blank', 'noopener,noreferrer')
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } finally {
      setOpeningCv(false)
    }
  }

  const copyEmail = async () => {
    if (!profile.email) return
    try {
      await navigator.clipboard.writeText(profile.email)
      setCopiedEmail(true)
      window.setTimeout(() => setCopiedEmail(false), 1800)
    } catch {
      // Clipboard unavailable in insecure context
    }
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Hero Dossier Header */}
      <div className="overflow-hidden rounded-2xl border border-stone-200/80 bg-white shadow-card">
        <div className="relative h-24 mesh-hero bg-dots">
          <div className="absolute inset-0 bg-gradient-to-b from-transparent to-white/55" />
        </div>

        <div className="relative z-10 px-6 pb-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
              {blindMode ? (
                <div className="-mt-12 flex h-20 w-20 shrink-0 items-center justify-center rounded-2xl bg-amber-100 text-amber-700 ring-4 ring-white shadow-md">
                  <EyeOff size={28} />
                </div>
              ) : (
                <Avatar
                  name={profile.full_name}
                  size="xl"
                  className="-mt-12 ring-4 ring-white shadow-md"
                />
              )}
              <div className="space-y-1.5 pt-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-2xl font-bold tracking-tight text-slate-900">
                    {profile.full_name || 'Unnamed Candidate'}
                  </h2>
                  <Badge variant="brand">{profile.primary_domain || 'General'}</Badge>
                  <Badge variant="secondary">{seniority}</Badge>
                </div>

                {currentRole && (
                  <p className="text-sm font-medium text-slate-600">
                    {currentRole.title}
                    {currentRole.company ? (
                      <>
                        {' '}
                        <span className="text-slate-400">at</span>{' '}
                        <span className="text-slate-900">{currentRole.company}</span>
                      </>
                    ) : null}
                  </p>
                )}

                <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-1 text-xs text-slate-500">
                  {profile.city && (
                    <span className="inline-flex items-center gap-1">
                      <MapPin size={13} className="text-slate-400" />
                      {profile.city}
                    </span>
                  )}
                  {profile.email && (
                    <span className="inline-flex items-center gap-1">
                      <Mail size={13} className="text-slate-400" />
                      <a
                        href={`mailto:${profile.email}`}
                        className="font-medium text-slate-700 hover:text-brand-600"
                      >
                        {profile.email}
                      </a>
                      <button
                        type="button"
                        onClick={copyEmail}
                        className="ml-0.5 rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                        title="Copy email"
                      >
                        {copiedEmail ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                      </button>
                    </span>
                  )}
                  {profile.phone && (
                    <a
                      href={`tel:${profile.phone}`}
                      className="inline-flex items-center gap-1 font-medium text-slate-700 hover:text-brand-600"
                    >
                      <Phone size={13} className="text-slate-400" />
                      {profile.phone}
                    </a>
                  )}
                  {createdAt && (
                    <span className="text-slate-400">Added {formatLongDate(createdAt)}</span>
                  )}
                  {profile.source && (
                    <Badge variant="secondary" className="capitalize">
                      Source: {profile.source}
                    </Badge>
                  )}
                  {profile.consent_given_at && (
                    <Badge variant="success">
                      Consent: {formatDate(profile.consent_given_at)}
                    </Badge>
                  )}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3 lg:pt-3">
              <CompletenessRing score={completeness.score} missing={completeness.missing} />
              {headerActions}
            </div>
          </div>

          {/* External Links & Saved CV Bar */}
          {!blindMode &&
            (profile.linkedin_url || profile.github_url || profile.portfolio_url || resumeFileId) && (
            <div className="mt-5 flex flex-wrap gap-2 border-t border-slate-100 pt-4">
              {resumeFileId && (
                <button
                  type="button"
                  onClick={openSavedResume}
                  disabled={openingCv}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50/80 px-3 py-1.5 text-xs font-semibold text-emerald-800 transition hover:border-emerald-300 hover:bg-emerald-100 disabled:opacity-60"
                >
                  <FileText size={13} />
                  {openingCv ? 'Opening CV…' : sourceFilename || 'Saved Resume / CV'}
                  <ExternalLink size={11} className="opacity-70" />
                </button>
              )}
              {profile.linkedin_url && (
                <a
                  href={ensureProtocol(profile.linkedin_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
                >
                  <Linkedin size={13} />
                  {prettyUrl(profile.linkedin_url)}
                  <ExternalLink size={11} className="opacity-60" />
                </a>
              )}
              {profile.github_url && (
                <a
                  href={ensureProtocol(profile.github_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
                >
                  <Github size={13} />
                  {prettyUrl(profile.github_url)}
                  <ExternalLink size={11} className="opacity-60" />
                </a>
              )}
              {profile.portfolio_url && (
                <a
                  href={ensureProtocol(profile.portfolio_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700"
                >
                  <Globe size={13} />
                  {prettyUrl(profile.portfolio_url)}
                  <ExternalLink size={11} className="opacity-60" />
                </a>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Quick Profile KPI Strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          {
            label: 'Experience',
            value: formatYears(profile.years_experience),
            sub: seniority,
            icon: Briefcase,
            tint: 'bg-sky-50 text-sky-600',
          },
          {
            label: 'Career Roles',
            value: String(profile.work_experience.length),
            sub: currentRole?.company || 'Work history',
            icon: Sparkles,
            tint: 'bg-brand-50 text-brand-600',
          },
          {
            label: 'Tech & Tools',
            value: String(profile.technical_skills.length + profile.tools.length),
            sub: `${profile.technical_skills.length} tech · ${profile.tools.length} tools`,
            icon: Code2,
            tint: 'bg-violet-50 text-violet-600',
          },
          {
            label: 'Credentials',
            value: String(profile.education.length + profile.certifications.length),
            sub: `${profile.education.length} edu · ${profile.certifications.length} cert`,
            icon: GraduationCap,
            tint: 'bg-amber-50 text-amber-600',
          },
        ].map((item) => {
          const Icon = item.icon
          return (
            <div key={item.label} className="rounded-2xl border bg-white p-4 shadow-card">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-500">{item.label}</span>
                <span className={cn('flex h-8 w-8 items-center justify-center rounded-lg', item.tint)}>
                  <Icon size={15} />
                </span>
              </div>
              <p className="mt-2 text-2xl font-bold tracking-tight text-slate-900">{item.value}</p>
              <p className="mt-0.5 truncate text-xs text-slate-500">{item.sub}</p>
            </div>
          )
        })}
      </div>

      {/* Interactive Network Graph */}
      {showGraph && <CandidateNetworkGraph profile={profile} />}

      {/* Main Two-Column Detailed Dossier */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left 8 Cols: Executive Summary + Experience Timeline */}
        <div className="space-y-6 lg:col-span-8">
          {/* Executive Summary */}
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center gap-2">
                <Sparkles size={16} className="text-brand-600" />
                <CardTitle>Executive Summary</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-7 text-slate-700">
                {profile.profile_summary || 'No summary extracted for this candidate.'}
              </p>
            </CardContent>
          </Card>

          {/* Career Trajectory Timeline */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Briefcase size={16} className="text-sky-600" />
                  <CardTitle>Career Trajectory</CardTitle>
                </div>
                <Badge variant="secondary">
                  {profile.work_experience.length} position{profile.work_experience.length === 1 ? '' : 's'}
                </Badge>
              </div>
            </CardHeader>
            <CardContent>
              {profile.work_experience.length === 0 ? (
                <p className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
                  No work experience entries recorded.
                </p>
              ) : (
                <div className="relative space-y-6 pl-6 before:absolute before:bottom-2 before:left-[9px] before:top-2 before:w-px before:bg-slate-200">
                  {profile.work_experience.map((exp, idx) => {
                    const active = isCurrentRole(exp.end_date)
                    const roleSkills = detectRoleSkills(exp.bullets || [], exp.job_title, allCapabilities)
                    return (
                      <div key={idx} className="relative">
                        <span
                          className={cn(
                            'absolute -left-6 top-1.5 flex h-[19px] w-[19px] items-center justify-center rounded-full border-2 border-white shadow-sm',
                            active ? 'bg-emerald-500' : 'bg-brand-500',
                          )}
                        >
                          <span className="h-1.5 w-1.5 rounded-full bg-white" />
                        </span>

                        <div className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 transition hover:border-slate-300/90 hover:bg-white">
                          <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                              <div className="flex flex-wrap items-center gap-2">
                                <h4 className="text-[15px] font-semibold text-slate-900">
                                  {exp.job_title || 'Untitled Role'}
                                </h4>
                                {formatEmploymentType(exp.employment_type) && (
                                  <Badge variant="outline" className="text-[10px]">
                                    {formatEmploymentType(exp.employment_type)}
                                  </Badge>
                                )}
                              </div>
                              <p className="text-sm font-medium text-brand-700">{exp.company}</p>
                            </div>
                            <div className="flex items-center gap-1.5">
                              {active && <Badge variant="success">Current</Badge>}
                              <span className="rounded-md border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-medium text-slate-600">
                                {formatDate(exp.start_date)} – {formatDate(exp.end_date)}
                              </span>
                            </div>
                          </div>

                          {exp.bullets && exp.bullets.length > 0 && (
                            <ul className="mt-3 space-y-1.5 text-sm leading-6 text-slate-600">
                              {exp.bullets.map((bullet, bi) => (
                                <li key={bi} className="flex gap-2.5">
                                  <span className="mt-2.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-400" />
                                  <span>{bullet}</span>
                                </li>
                              ))}
                            </ul>
                          )}

                          {roleSkills.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-200/70 pt-3">
                              {roleSkills.map((sk) => (
                                <span
                                  key={sk}
                                  className="rounded-md bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700"
                                >
                                  {sk}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Projects */}
          {profile.projects && profile.projects.length > 0 && (
            <Card>
              <CardHeader className="pb-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FolderGit2 size={16} className="text-brand-600" />
                    <CardTitle>Projects</CardTitle>
                  </div>
                  <Badge variant="secondary">
                    {profile.projects.length} project{profile.projects.length === 1 ? '' : 's'}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {profile.projects.map((proj, idx) => (
                  <div
                    key={idx}
                    className="rounded-xl border border-slate-200/80 bg-slate-50/50 p-4 space-y-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h4 className="text-sm font-semibold text-slate-900">
                        {proj.name || 'Untitled Project'}
                      </h4>
                      {(proj.start_date || proj.end_date) && (
                        <span className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-500">
                          {[proj.start_date, proj.end_date].filter(Boolean).join(' – ')}
                        </span>
                      )}
                    </div>
                    {proj.description && (
                      <p className="text-xs leading-5 text-slate-600">{proj.description}</p>
                    )}
                    {proj.technologies && proj.technologies.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {proj.technologies.map((tech, ti) => (
                          <span
                            key={ti}
                            className="rounded-md bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700"
                          >
                            {tech}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Education */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <GraduationCap size={16} className="text-amber-600" />
                <CardTitle>Education</CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {profile.education.length === 0 ? (
                <p className="text-sm text-slate-500">No education entries recorded.</p>
              ) : (
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {profile.education.map((edu, idx) => {
                    const endYr = edu.end_year ?? edu.graduation_year
                    const dateLabel = edu.is_current
                      ? edu.start_year
                        ? `${edu.start_year} – Present`
                        : endYr
                          ? `Expected ${endYr}`
                          : 'Pursuing'
                      : edu.start_year && endYr
                        ? `${edu.start_year} – ${endYr}`
                        : endYr
                          ? `Class of ${endYr}`
                          : null
                    return (
                      <div
                        key={idx}
                        className="flex items-start gap-3 rounded-xl border border-slate-200/80 bg-amber-50/30 p-4"
                      >
                        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-100/80 text-amber-700">
                          <GraduationCap size={18} />
                        </div>
                        <div className="min-w-0">
                          <p className="text-sm font-semibold text-slate-900">
                            {edu.degree || 'Degree'}
                            {edu.field_of_study ? ` · ${edu.field_of_study}` : ''}
                          </p>
                          <p className="text-xs font-medium text-slate-600">
                            {blindMode ? '[Institution Redacted]' : edu.institution}
                          </p>
                          {dateLabel && (
                            <p className="mt-1 text-xs text-slate-500">{dateLabel}</p>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right 4 Cols: Skills Matrix, Credentials & Original Resume */}
        <div className="space-y-6 lg:col-span-4">
          {/* Skills & Capabilities */}
          <Card>
            <CardHeader className="pb-4">
              <div className="flex items-center gap-2">
                <Code2 size={16} className="text-violet-600" />
                <CardTitle>Skills & Capabilities</CardTitle>
              </div>
            </CardHeader>
            <CardContent className="space-y-5">
              <div>
                <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <span className="inline-flex items-center gap-1.5">
                    <Code2 size={13} className="text-violet-500" /> Technical Skills
                  </span>
                  <span>{profile.technical_skills.length}</span>
                </div>
                {profile.technical_skills.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {profile.technical_skills.map((skill, i) => {
                      const sources = evidenceMap.get(skill.toLowerCase())
                      const evidenced = Boolean(sources && sources.length > 0)
                      const tooltip = !hasEvidenceData
                        ? undefined
                        : evidenced
                          ? `Evidenced in: ${sources!.map((s) => EVIDENCE_SOURCE_LABELS[s] || s).join(', ')}`
                          : 'Not evidenced in experience, projects, or credentials'
                      return (
                        <span
                          key={i}
                          title={tooltip}
                          className={cn(
                            'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium',
                            !hasEvidenceData || evidenced
                              ? 'border-violet-200/80 bg-violet-50 text-violet-800'
                              : 'border-dashed border-slate-300 bg-slate-50 text-slate-600',
                          )}
                        >
                          {hasEvidenceData && (
                            <span
                              className={cn(
                                'h-1.5 w-1.5 rounded-full shrink-0',
                                evidenced ? 'bg-emerald-500' : 'bg-slate-300',
                              )}
                              aria-hidden="true"
                            />
                          )}
                          {skill}
                        </span>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">None listed</p>
                )}
              </div>

              <div className="border-t border-slate-100 pt-4">
                <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <span className="inline-flex items-center gap-1.5">
                    <Wrench size={13} className="text-emerald-600" /> Tools & Platforms
                  </span>
                  <span>{profile.tools.length}</span>
                </div>
                {profile.tools.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {profile.tools.map((tool, i) => {
                      const sources = evidenceMap.get(tool.toLowerCase())
                      const evidenced = Boolean(sources && sources.length > 0)
                      const tooltip = !hasEvidenceData
                        ? undefined
                        : evidenced
                          ? `Evidenced in: ${sources!.map((s) => EVIDENCE_SOURCE_LABELS[s] || s).join(', ')}`
                          : 'Not evidenced in experience, projects, or credentials'
                      return (
                        <span
                          key={i}
                          title={tooltip}
                          className={cn(
                            'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-medium',
                            !hasEvidenceData || evidenced
                              ? 'border-emerald-200/80 bg-emerald-50 text-emerald-800'
                              : 'border-dashed border-slate-300 bg-slate-50 text-slate-600',
                          )}
                        >
                          {hasEvidenceData && (
                            <span
                              className={cn(
                                'h-1.5 w-1.5 rounded-full shrink-0',
                                evidenced ? 'bg-emerald-500' : 'bg-slate-300',
                              )}
                              aria-hidden="true"
                            />
                          )}
                          {tool}
                        </span>
                      )
                    })}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">None listed</p>
                )}
                {hasEvidenceData && (
                  <p className="mt-2.5 flex items-center gap-3 text-[11px] text-slate-400">
                    <span className="inline-flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                      Evidenced in CV (hover for section)
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className="h-1.5 w-1.5 rounded-full bg-slate-300" />
                      Skills list only
                    </span>
                  </p>
                )}
              </div>

              <div className="border-t border-slate-100 pt-4">
                <div className="mb-2 flex items-center justify-between text-xs font-semibold uppercase tracking-wider text-slate-500">
                  <span className="inline-flex items-center gap-1.5">
                    <Users size={13} className="text-slate-500" /> Soft Skills
                  </span>
                  <span>{profile.soft_skills.length}</span>
                </div>
                {profile.soft_skills.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {profile.soft_skills.map((soft, i) => (
                      <Badge key={i} variant="outline">
                        {soft}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400">None listed</p>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Certifications, Languages & Interests */}
          {(profile.certifications.length > 0 ||
            profile.languages.length > 0 ||
            profile.hobbies_interests.length > 0) && (
            <Card>
              <CardHeader className="pb-4">
                <div className="flex items-center gap-2">
                  <Award size={16} className="text-rose-500" />
                  <CardTitle>Credentials & Additional</CardTitle>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {profile.certifications.length > 0 && (
                  <div>
                    <p className="mb-2 inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      <Award size={13} className="text-rose-500" /> Certifications
                    </p>
                    <ul className="space-y-1.5">
                      {profile.certifications.map((cert, i) => (
                        <li
                          key={i}
                          className="rounded-lg border border-rose-100 bg-rose-50/50 px-3 py-2 text-xs font-medium text-rose-900"
                        >
                          {cert}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {profile.languages.length > 0 && (
                  <div className={profile.certifications.length ? 'border-t border-slate-100 pt-4' : ''}>
                    <p className="mb-2 inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      <Languages size={13} className="text-sky-600" /> Languages
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {profile.languages.map((lang, i) => (
                        <Badge key={i} variant="secondary">
                          {lang}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {profile.hobbies_interests.length > 0 && (
                  <div
                    className={
                      profile.certifications.length || profile.languages.length
                        ? 'border-t border-slate-100 pt-4'
                        : ''
                    }
                  >
                    <p className="mb-2 inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
                      <Heart size={13} className="text-pink-500" /> Interests
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {profile.hobbies_interests.map((item, i) => (
                        <Badge key={i} variant="outline">
                          {item}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Compensation & Mobility */}
          {(profile.notice_period_days != null ||
            (profile.preferred_locations && profile.preferred_locations.length > 0) ||
            profile.open_to_relocate != null ||
            (canWrite && (profile.current_ctc != null || profile.expected_ctc != null))) && (
            <Card>
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Briefcase size={16} className="text-emerald-600" />
                    <CardTitle>Compensation & Mobility</CardTitle>
                  </div>
                  {canWrite && (profile.current_ctc != null || profile.expected_ctc != null) && (
                    <Badge variant="secondary" className="text-[10px]">
                      Recruiter/Admin
                    </Badge>
                  )}
                </div>
              </CardHeader>
              <CardContent className="space-y-2.5 text-sm">
                {profile.notice_period_days != null && (
                  <div className="flex justify-between gap-2 border-b border-slate-100 pb-2">
                    <span className="text-slate-500">Notice Period</span>
                    <span className="font-semibold text-slate-900">
                      {profile.notice_period_days} day{profile.notice_period_days === 1 ? '' : 's'}
                    </span>
                  </div>
                )}
                {canWrite && profile.current_ctc != null && (
                  <div className="flex justify-between gap-2 border-b border-slate-100 pb-2">
                    <span className="text-slate-500">Current CTC</span>
                    <span className="font-semibold text-slate-900">
                      {formatCtc(profile.current_ctc, profile.ctc_currency)}
                    </span>
                  </div>
                )}
                {canWrite && profile.expected_ctc != null && (
                  <div className="flex justify-between gap-2 border-b border-slate-100 pb-2">
                    <span className="text-slate-500">Expected CTC</span>
                    <span className="font-semibold text-emerald-700">
                      {formatCtc(profile.expected_ctc, profile.ctc_currency)}
                    </span>
                  </div>
                )}
                {profile.open_to_relocate != null && (
                  <div className="flex justify-between gap-2 border-b border-slate-100 pb-2">
                    <span className="text-slate-500">Open to Relocate</span>
                    <Badge variant={profile.open_to_relocate ? 'success' : 'secondary'}>
                      {profile.open_to_relocate ? 'Yes' : 'No'}
                    </Badge>
                  </div>
                )}
                {profile.preferred_locations && profile.preferred_locations.length > 0 && (
                  <div className="pt-1">
                    <p className="mb-1.5 text-xs font-medium text-slate-500">Preferred Locations</p>
                    <div className="flex flex-wrap gap-1.5">
                      {profile.preferred_locations.map((loc, i) => (
                        <Badge key={i} variant="outline">
                          {loc}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Original Resume Card */}
          <ResumePreview
            resumeFileId={resumeFileId ?? null}
            originalFilename={sourceFilename}
            storedFilename={storedFilename}
          />
        </div>
      </div>
    </div>
  )
}
