import { Link } from 'react-router-dom'
import { ArrowUpRight, Briefcase, FileText, Mail, MapPin } from 'lucide-react'
import type { CandidateListItem } from '@/types'
import { formatRelativeDate, formatYears } from '@/lib/utils'
import { getSeniority } from '@/lib/profile'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'

interface CandidateCardProps {
  candidate: CandidateListItem
}

export function CandidateCard({ candidate }: CandidateCardProps) {
  const roleLine = [candidate.current_title, candidate.current_company].filter(Boolean).join(' · ')

  return (
    <Link to={`/candidates/${candidate.id}`} className="group block h-full">
      <article className="flex h-full flex-col justify-between rounded-2xl border border-slate-200/80 bg-white p-5 shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lg">
        <div>
          {/* Top row */}
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <Avatar name={candidate.full_name} size="md" />
              <div className="min-w-0">
                <h3 className="truncate text-[15px] font-semibold text-slate-900 transition group-hover:text-brand-600">
                  {candidate.full_name}
                </h3>
                <p className="truncate text-xs text-slate-500">
                  {roleLine || candidate.email || 'No email provided'}
                </p>
              </div>
            </div>
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-slate-300 transition group-hover:bg-brand-50 group-hover:text-brand-600">
              <ArrowUpRight size={16} />
            </span>
          </div>

          {/* Domain + Experience Pills */}
          <div className="mt-4 flex flex-wrap items-center gap-1.5">
            <Badge variant="brand">{candidate.primary_domain}</Badge>
            <Badge variant="secondary">
              <Briefcase size={11} />
              {formatYears(candidate.years_experience)} · {getSeniority(candidate.years_experience)}
            </Badge>
          </div>

          {/* Contact / Location metadata */}
          {(candidate.city || (roleLine && candidate.email)) && (
            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
              {candidate.city && (
                <span className="inline-flex items-center gap-1">
                  <MapPin size={12} className="text-slate-400" />
                  {candidate.city}
                </span>
              )}
              {roleLine && candidate.email && (
                <span className="inline-flex min-w-0 items-center gap-1 truncate">
                  <Mail size={12} className="shrink-0 text-slate-400" />
                  <span className="truncate">{candidate.email}</span>
                </span>
              )}
            </div>
          )}

          {/* Skills */}
          {candidate.technical_skills.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-1.5">
              {candidate.technical_skills.slice(0, 4).map((skill, i) => (
                <span
                  key={i}
                  className="rounded-md border border-slate-200/80 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-600"
                >
                  {skill}
                </span>
              ))}
              {candidate.technical_skills.length > 4 && (
                <span className="rounded-md bg-brand-50 px-2 py-0.5 text-[11px] font-semibold text-brand-700">
                  +{candidate.technical_skills.length - 4}
                </span>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="mt-5 flex items-center justify-between gap-2 border-t border-slate-100 pt-3 text-xs text-slate-400">
          <div className="flex min-w-0 items-center gap-2">
            <span className="shrink-0">Added {formatRelativeDate(candidate.created_at)}</span>
            {candidate.resume_file_id && (
              <span
                className="inline-flex min-w-0 items-center gap-1 rounded-md bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700"
                title={candidate.resume_filename || 'Saved CV attached'}
              >
                <FileText size={11} className="shrink-0" />
                <span className="truncate max-w-[110px]">
                  {candidate.resume_filename || 'CV saved'}
                </span>
              </span>
            )}
          </div>
          <span className="shrink-0 font-medium text-brand-600 opacity-0 transition group-hover:opacity-100">
            View profile →
          </span>
        </div>
      </article>
    </Link>
  )
}
