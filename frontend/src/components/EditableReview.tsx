import { useState } from 'react'
import {
  AlertTriangle,
  Award,
  Briefcase,
  Code2,
  GraduationCap,
  Plus,
  Save,
  Trash2,
  User,
} from 'lucide-react'
import type { CandidateUpdate, DuplicateInfo, ParsedResumeData } from '@/types'
import {
  getSourceFilename,
  getStoredFilename,
  normalizeProfile,
  toCandidatePayload,
  validateProfile,
  type FormErrors,
} from '@/lib/profile'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Label } from '@/components/ui/Label'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { TagInput } from '@/components/ui/TagInput'
import { ResumePreview } from '@/components/ResumePreview'

interface EditableReviewProps {
  parsedData: ParsedResumeData
  duplicate?: DuplicateInfo | null
  resumeFileId?: string | null
  onSave: (payload: CandidateUpdate) => Promise<void>
  onCancel?: () => void
  onChange?: (draft: ParsedResumeData) => void
  saving: boolean
  submitLabel?: string
  cancelLabel?: string
}

export function EditableReview({
  parsedData,
  duplicate,
  resumeFileId,
  onSave,
  onCancel,
  onChange,
  saving,
  submitLabel = 'Save Candidate',
  cancelLabel = 'Back',
}: EditableReviewProps) {
  const [form, setForm] = useState<ParsedResumeData>(() => normalizeProfile(parsedData))
  const [errors, setErrors] = useState<FormErrors>({})

  const updateForm = (updater: (prev: ParsedResumeData) => ParsedResumeData) => {
    setForm((prev) => {
      const next = updater(prev)
      onChange?.(next)
      return next
    })
  }

  const handleField = <K extends keyof ParsedResumeData>(key: K, value: ParsedResumeData[K]) => {
    updateForm((prev) => ({ ...prev, [key]: value }))
    if (key in errors) {
      setErrors((prev) => {
        const copy = { ...prev }
        delete copy[key as keyof FormErrors]
        return copy
      })
    }
  }

  const handleWorkField = (
    idx: number,
    field: 'company' | 'job_title' | 'start_date' | 'end_date',
    value: string | null,
  ) => {
    updateForm((prev) => {
      const work = [...prev.work_experience]
      work[idx] = { ...work[idx], [field]: value }
      return { ...prev, work_experience: work }
    })
  }

  const handleBullet = (expIdx: number, bulletIdx: number, value: string) => {
    updateForm((prev) => {
      const work = [...prev.work_experience]
      const bullets = [...work[expIdx].bullets]
      bullets[bulletIdx] = value
      work[expIdx] = { ...work[expIdx], bullets }
      return { ...prev, work_experience: work }
    })
  }

  const addBullet = (expIdx: number) => {
    updateForm((prev) => {
      const work = [...prev.work_experience]
      work[expIdx] = { ...work[expIdx], bullets: [...work[expIdx].bullets, ''] }
      return { ...prev, work_experience: work }
    })
  }

  const removeBullet = (expIdx: number, bulletIdx: number) => {
    updateForm((prev) => {
      const work = [...prev.work_experience]
      work[expIdx] = {
        ...work[expIdx],
        bullets: work[expIdx].bullets.filter((_, i) => i !== bulletIdx),
      }
      return { ...prev, work_experience: work }
    })
  }

  const handleEduField = (
    idx: number,
    field: 'degree' | 'institution' | 'graduation_year',
    value: string | number | null,
  ) => {
    updateForm((prev) => {
      const edu = [...prev.education]
      edu[idx] = { ...edu[idx], [field]: value }
      return { ...prev, education: edu }
    })
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const nextErrors = validateProfile(form)
    setErrors(nextErrors)
    if (Object.keys(nextErrors).length > 0) return
    await onSave(toCandidatePayload(form))
  }

  const storedFilename = getStoredFilename(form.raw_parsed_data)
  const sourceFilename = getSourceFilename(form.raw_parsed_data)

  return (
    <form onSubmit={handleSubmit} className="grid grid-cols-1 gap-6 lg:grid-cols-12">
      {/* Main Form */}
      <div className="space-y-6 lg:col-span-8">
        {duplicate?.is_duplicate && (
          <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-amber-900">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-600" />
            <div>
              <p className="font-semibold">
                Potential duplicate matched by {duplicate.matched_field}
              </p>
              <p className="mt-0.5 text-xs text-amber-800">
                Verify the email and phone fields below. Saving with the same email or phone as an
                existing record will be rejected to prevent duplicate profiles.
              </p>
            </div>
          </div>
        )}

        {/* Identity & Contact */}
        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <User size={16} className="text-brand-600" />
              <CardTitle>Identity & Contact Details</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="full_name">Full Name *</Label>
                <Input
                  id="full_name"
                  value={form.full_name}
                  onChange={(e) => handleField('full_name', e.target.value)}
                  placeholder="Jane Doe"
                />
                {errors.full_name && <p className="text-xs text-red-600">{errors.full_name}</p>}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="email">Email Address</Label>
                <Input
                  id="email"
                  type="email"
                  value={form.email ?? ''}
                  onChange={(e) => handleField('email', e.target.value || null)}
                  placeholder="jane@company.com"
                />
                {errors.email && <p className="text-xs text-red-600">{errors.email}</p>}
              </div>
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="phone">Phone</Label>
                <Input
                  id="phone"
                  value={form.phone ?? ''}
                  onChange={(e) => handleField('phone', e.target.value || null)}
                  placeholder="+1 555 0100"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="city">City / Location</Label>
                <Input
                  id="city"
                  value={form.city ?? ''}
                  onChange={(e) => handleField('city', e.target.value || null)}
                  placeholder="San Francisco, CA"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="years_experience">Years of Experience *</Label>
                <Input
                  id="years_experience"
                  type="number"
                  step="0.5"
                  min={0}
                  value={String(form.years_experience)}
                  onChange={(e) => handleField('years_experience', parseFloat(e.target.value) || 0)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="primary_domain">Primary Domain *</Label>
              <Input
                id="primary_domain"
                value={form.primary_domain}
                onChange={(e) => handleField('primary_domain', e.target.value)}
                placeholder="e.g. Software Engineering, Product Design, Data Science"
              />
              {errors.primary_domain && (
                <p className="text-xs text-red-600">{errors.primary_domain}</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="profile_summary">Executive Summary *</Label>
              <Textarea
                id="profile_summary"
                rows={3}
                value={form.profile_summary}
                onChange={(e) => handleField('profile_summary', e.target.value)}
                placeholder="Concise 2-3 sentence candidate overview…"
              />
              {errors.profile_summary && (
                <p className="text-xs text-red-600">{errors.profile_summary}</p>
              )}
            </div>

            <div className="grid grid-cols-1 gap-4 border-t border-slate-100 pt-4 sm:grid-cols-3">
              <div className="space-y-1.5">
                <Label htmlFor="linkedin_url">LinkedIn URL</Label>
                <Input
                  id="linkedin_url"
                  value={form.linkedin_url ?? ''}
                  onChange={(e) => handleField('linkedin_url', e.target.value || null)}
                  placeholder="https://linkedin.com/in/..."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="github_url">GitHub URL</Label>
                <Input
                  id="github_url"
                  value={form.github_url ?? ''}
                  onChange={(e) => handleField('github_url', e.target.value || null)}
                  placeholder="https://github.com/..."
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="portfolio_url">Portfolio URL</Label>
                <Input
                  id="portfolio_url"
                  value={form.portfolio_url ?? ''}
                  onChange={(e) => handleField('portfolio_url', e.target.value || null)}
                  placeholder="https://..."
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Skills & Tags */}
        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Code2 size={16} className="text-violet-600" />
                <CardTitle>Skills & Capabilities</CardTitle>
              </div>
              <span className="text-xs text-slate-400">Press Enter or comma to add</span>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-1.5">
              <Label>Technical Skills</Label>
              <TagInput
                value={form.technical_skills}
                onChange={(next) => handleField('technical_skills', next)}
                placeholder="Python, React, PostgreSQL…"
                tone={{ bg: '#f5f3ff', text: '#5b21b6' }}
              />
            </div>

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Tools & Platforms</Label>
                <TagInput
                  value={form.tools}
                  onChange={(next) => handleField('tools', next)}
                  placeholder="AWS, Docker, Figma…"
                  tone={{ bg: '#ecfdf5', text: '#065f46' }}
                />
              </div>
              <div className="space-y-1.5">
                <Label>Soft Skills</Label>
                <TagInput
                  value={form.soft_skills}
                  onChange={(next) => handleField('soft_skills', next)}
                  placeholder="Leadership, Communication…"
                  tone={{ bg: '#f1f5f9', text: '#334155' }}
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Work Experience */}
        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Briefcase size={16} className="text-sky-600" />
                <CardTitle>Work Experience</CardTitle>
                <Badge variant="secondary">{form.work_experience.length}</Badge>
              </div>
              <Button
                type="button"
                variant="soft"
                size="sm"
                onClick={() =>
                  updateForm((prev) => ({
                    ...prev,
                    work_experience: [
                      ...prev.work_experience,
                      { company: '', job_title: '', start_date: '', end_date: '', bullets: [''] },
                    ],
                  }))
                }
              >
                <Plus size={14} /> Add role
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {form.work_experience.length === 0 ? (
              <p className="rounded-xl border border-dashed border-slate-200 p-6 text-center text-sm text-slate-500">
                No roles yet. Click “Add role” to record work history.
              </p>
            ) : (
              form.work_experience.map((exp, i) => (
                <div
                  key={i}
                  className="space-y-3 rounded-xl border border-slate-200 bg-slate-50/50 p-4"
                >
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                      Role {i + 1}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        updateForm((prev) => ({
                          ...prev,
                          work_experience: prev.work_experience.filter((_, idx) => idx !== i),
                        }))
                      }
                      className="inline-flex items-center gap-1 text-xs font-medium text-red-600 hover:text-red-700"
                    >
                      <Trash2 size={13} /> Remove
                    </button>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <Label className="text-xs">Job Title</Label>
                      <Input
                        value={exp.job_title}
                        onChange={(e) => handleWorkField(i, 'job_title', e.target.value)}
                        placeholder="Senior Software Engineer"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">Company</Label>
                      <Input
                        value={exp.company}
                        onChange={(e) => handleWorkField(i, 'company', e.target.value)}
                        placeholder="Acme Corp"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <Label className="text-xs">Start Date</Label>
                      <Input
                        value={exp.start_date ?? ''}
                        onChange={(e) => handleWorkField(i, 'start_date', e.target.value || null)}
                        placeholder="Jan 2021"
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-xs">End Date</Label>
                      <Input
                        value={exp.end_date ?? ''}
                        onChange={(e) => handleWorkField(i, 'end_date', e.target.value || null)}
                        placeholder="Present"
                      />
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label className="text-xs">Key Impact Bullets</Label>
                    {exp.bullets.map((b, bi) => (
                      <div key={bi} className="flex items-center gap-2">
                        <Input
                          value={b}
                          onChange={(e) => handleBullet(i, bi, e.target.value)}
                          placeholder="Describe impact or achievement…"
                        />
                        <button
                          type="button"
                          onClick={() => removeBullet(i, bi)}
                          className="rounded-lg p-2 text-slate-400 hover:bg-slate-200/70 hover:text-red-600"
                          aria-label="Remove bullet"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                    <button
                      type="button"
                      onClick={() => addBullet(i)}
                      className="inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700"
                    >
                      <Plus size={13} /> Add bullet
                    </button>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Education */}
        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <GraduationCap size={16} className="text-amber-600" />
                <CardTitle>Education</CardTitle>
                <Badge variant="secondary">{form.education.length}</Badge>
              </div>
              <Button
                type="button"
                variant="soft"
                size="sm"
                onClick={() =>
                  updateForm((prev) => ({
                    ...prev,
                    education: [
                      ...prev.education,
                      { degree: '', institution: '', graduation_year: null },
                    ],
                  }))
                }
              >
                <Plus size={14} /> Add education
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            {form.education.length === 0 ? (
              <p className="text-sm text-slate-500">No education entries recorded.</p>
            ) : (
              form.education.map((edu, i) => (
                <div
                  key={i}
                  className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-slate-50/50 p-3.5 sm:grid-cols-12 sm:items-end"
                >
                  <div className="space-y-1 sm:col-span-5">
                    <Label className="text-xs">Degree</Label>
                    <Input
                      value={edu.degree}
                      onChange={(e) => handleEduField(i, 'degree', e.target.value)}
                      placeholder="B.S. Computer Science"
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-4">
                    <Label className="text-xs">Institution</Label>
                    <Input
                      value={edu.institution}
                      onChange={(e) => handleEduField(i, 'institution', e.target.value)}
                      placeholder="University"
                    />
                  </div>
                  <div className="space-y-1 sm:col-span-2">
                    <Label className="text-xs">Year</Label>
                    <Input
                      type="number"
                      value={edu.graduation_year != null ? String(edu.graduation_year) : ''}
                      onChange={(e) =>
                        handleEduField(
                          i,
                          'graduation_year',
                          e.target.value ? parseInt(e.target.value, 10) : null,
                        )
                      }
                      placeholder="2020"
                    />
                  </div>
                  <div className="flex justify-end sm:col-span-1">
                    <button
                      type="button"
                      onClick={() =>
                        updateForm((prev) => ({
                          ...prev,
                          education: prev.education.filter((_, idx) => idx !== i),
                        }))
                      }
                      className="rounded-lg p-2 text-slate-400 hover:bg-red-50 hover:text-red-600"
                      aria-label="Remove education"
                    >
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        {/* Additional Credentials */}
        <Card>
          <CardHeader className="pb-4">
            <div className="flex items-center gap-2">
              <Award size={16} className="text-rose-500" />
              <CardTitle>Credentials & Additional Info</CardTitle>
            </div>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="space-y-1.5">
              <Label>Certifications</Label>
              <TagInput
                value={form.certifications}
                onChange={(next) => handleField('certifications', next)}
                placeholder="AWS SAA…"
                tone={{ bg: '#fff1f2', text: '#9f1239' }}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Languages</Label>
              <TagInput
                value={form.languages}
                onChange={(next) => handleField('languages', next)}
                placeholder="English, Spanish…"
                tone={{ bg: '#f0f9ff', text: '#075985' }}
              />
            </div>
            <div className="space-y-1.5">
              <Label>Interests</Label>
              <TagInput
                value={form.hobbies_interests}
                onChange={(next) => handleField('hobbies_interests', next)}
                placeholder="Open source…"
              />
            </div>
          </CardContent>
        </Card>

        {/* Sticky Save Footer */}
        <div className="sticky bottom-4 z-10 flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-lg backdrop-blur">
          <p className="hidden text-xs text-slate-500 sm:block">
            Changes update the live candidate network graph automatically.
          </p>
          <div className="ml-auto flex items-center gap-2">
            {onCancel && (
              <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
                {cancelLabel}
              </Button>
            )}
            <Button type="submit" loading={saving}>
              <Save size={16} />
              {submitLabel}
            </Button>
          </div>
        </div>
      </div>

      {/* Right Column: Resume Source & Quick Audit */}
      <div className="space-y-6 lg:col-span-4">
        <div className="space-y-6 lg:sticky lg:top-6">
          <ResumePreview
            resumeFileId={resumeFileId ?? (storedFilename ? 'attached' : null)}
            originalFilename={sourceFilename}
            storedFilename={storedFilename}
          />

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm">Live Verification Snapshot</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex justify-between gap-2 border-b border-slate-100 pb-2">
                <span className="text-slate-500">Candidate</span>
                <span className="truncate font-semibold text-slate-900">
                  {form.full_name || '—'}
                </span>
              </div>
              <div className="flex justify-between gap-2 border-b border-slate-100 pb-2">
                <span className="text-slate-500">Domain</span>
                <span className="truncate font-medium text-brand-700">
                  {form.primary_domain || '—'}
                </span>
              </div>
              <div className="flex justify-between gap-2 border-b border-slate-100 pb-2">
                <span className="text-slate-500">Experience</span>
                <span className="font-medium text-slate-800">{form.years_experience} yrs</span>
              </div>
              <div className="flex justify-between gap-2 border-b border-slate-100 pb-2">
                <span className="text-slate-500">Roles / Education</span>
                <span className="font-medium text-slate-800">
                  {form.work_experience.length} / {form.education.length}
                </span>
              </div>
              <div className="flex justify-between gap-2">
                <span className="text-slate-500">Skills + Tools</span>
                <span className="font-medium text-slate-800">
                  {form.technical_skills.length + form.tools.length}
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </form>
  )
}
