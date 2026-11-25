import { Link } from 'react-router-dom'
import { ArrowUpRight, FileText } from 'lucide-react'
import type { CandidateListItem } from '@/types'
import { formatRelativeDate, formatYears } from '@/lib/utils'
import { getSeniority } from '@/lib/profile'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'

interface CandidateTableProps {
  candidates: CandidateListItem[]
}

export function CandidateTable({ candidates }: CandidateTableProps) {
  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200/80 bg-white shadow-card">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/70">
              <th className="px-5 py-3.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Candidate
              </th>
              <th className="px-5 py-3.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Domain
              </th>
              <th className="px-5 py-3.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Experience
              </th>
              <th className="px-5 py-3.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Technical Skills
              </th>
              <th className="px-5 py-3.5 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Added
              </th>
              <th className="px-5 py-3.5 text-right text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Profile
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {candidates.map((c) => {
              const roleLine = [c.current_title, c.current_company].filter(Boolean).join(' · ')
              return (
                <tr key={c.id} className="group transition hover:bg-brand-50/40">
                  <td className="px-5 py-4">
                    <Link to={`/candidates/${c.id}`} className="flex items-center gap-3">
                      <Avatar name={c.full_name} size="sm" />
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-slate-900 group-hover:text-brand-600">
                          {c.full_name}
                        </p>
                        <p className="truncate text-xs text-slate-500">
                          {roleLine || c.email || '—'}
                        </p>
                      </div>
                    </Link>
                  </td>
                  <td className="px-5 py-4">
                    <Badge variant="brand">{c.primary_domain}</Badge>
                  </td>
                  <td className="px-5 py-4">
                    <p className="text-sm font-medium text-slate-800">
                      {formatYears(c.years_experience)}
                    </p>
                    <p className="text-xs text-slate-500">{getSeniority(c.years_experience)}</p>
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex max-w-xs flex-wrap gap-1">
                      {c.technical_skills.slice(0, 3).map((s, idx) => (
                        <span
                          key={`${s}-${idx}`}
                          className="rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600"
                        >
                          {s}
                        </span>
                      ))}
                      {c.technical_skills.length > 3 && (
                        <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-600">
                          +{c.technical_skills.length - 3}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="whitespace-nowrap px-5 py-4 text-xs text-slate-500">
                    <div>{formatRelativeDate(c.created_at)}</div>
                    {c.resume_file_id && (
                      <div className="mt-1 inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
                        <FileText size={10} />
                        <span className="max-w-[120px] truncate">
                          {c.resume_filename || 'CV saved'}
                        </span>
                      </div>
                    )}
                  </td>
                  <td className="px-5 py-4 text-right">
                    <Link
                      to={`/candidates/${c.id}`}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 transition hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700"
                    >
                      Open
                      <ArrowUpRight size={13} />
                    </Link>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
