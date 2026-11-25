export type UserRole = 'admin' | 'recruiter' | 'viewer'

export interface User {
  id: string
  email: string
  full_name: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface WorkExperienceItem {
  company: string
  job_title: string
  start_date: string | null
  end_date: string | null
  bullets: string[]
}

export interface EducationItem {
  degree: string
  institution: string
  graduation_year: number | null
}

/** Shape shared by parsed resumes, saved candidates and the edit form. */
export interface CandidateProfileData {
  full_name: string
  email: string | null
  phone: string | null
  city: string | null
  linkedin_url: string | null
  github_url: string | null
  portfolio_url: string | null
  profile_summary: string
  years_experience: number
  primary_domain: string
  work_experience: WorkExperienceItem[]
  education: EducationItem[]
  technical_skills: string[]
  tools: string[]
  soft_skills: string[]
  hobbies_interests: string[]
  languages: string[]
  certifications: string[]
  notice_period_days?: number | null
  current_ctc?: number | null
  expected_ctc?: number | null
  ctc_currency?: string | null
  preferred_locations?: string[]
  open_to_relocate?: boolean | null
}

export interface ParsedResumeData extends CandidateProfileData {
  raw_parsed_data: Record<string, unknown>
}

export interface DuplicateMatch {
  candidate_id: string
  full_name: string
  email: string | null
  phone: string | null
  primary_domain: string
  matched_fields: string[]
  name_similarity: number | null
}

export interface DuplicateInfo {
  is_duplicate: boolean
  candidate_id: string | null
  matched_field: string | null
  matches: DuplicateMatch[]
}

export interface ResumeUploadResponse {
  resume_file_id: string
  parsed_data: ParsedResumeData
  duplicate: DuplicateInfo
  message: string
}

export interface CandidateListItem {
  id: string
  full_name: string
  email: string | null
  phone: string | null
  city?: string | null
  primary_domain: string
  years_experience: number
  technical_skills: string[]
  is_duplicate_flagged?: boolean
  resume_file_id?: string | null
  resume_filename?: string | null
  created_at: string
  current_title?: string | null
  current_company?: string | null
}

export interface PendingResumeItem {
  id: string
  original_filename: string
  file_size: number
  content_type: string
  status: string
  created_at: string
}

export interface CandidateResponse extends ParsedResumeData {
  id: string
  phone_normalized?: string | null
  resume_file_id: string | null
  is_duplicate_flagged: boolean
  created_at: string
  updated_at: string
}

export interface PaginatedCandidates {
  items: CandidateListItem[]
  total: number
  page: number
  page_size: number
  pages: number
}

export interface CandidateFilters {
  page?: number
  page_size?: number
  search?: string
  primary_domain?: string
  skills?: string
  min_years?: number
  max_years?: number
}

export interface NamedCount {
  name: string
  count: number
}

export interface CandidateStats {
  total: number
  avg_years_experience: number
  added_this_week: number
  domains: NamedCount[]
  top_skills: NamedCount[]
}

export interface CandidateUpdate {
  resume_file_id?: string | null
  full_name?: string
  email?: string | null
  phone?: string | null
  city?: string | null
  linkedin_url?: string | null
  github_url?: string | null
  portfolio_url?: string | null
  profile_summary?: string
  years_experience?: number
  primary_domain?: string
  work_experience?: WorkExperienceItem[]
  education?: EducationItem[]
  technical_skills?: string[]
  tools?: string[]
  soft_skills?: string[]
  hobbies_interests?: string[]
  languages?: string[]
  certifications?: string[]
  notice_period_days?: number | null
  current_ctc?: number | null
  expected_ctc?: number | null
  ctc_currency?: string | null
  preferred_locations?: string[]
  open_to_relocate?: boolean | null
  raw_parsed_data?: Record<string, unknown>
  allow_duplicate?: boolean
  is_duplicate_flagged?: boolean
}

export type JobStatus = 'draft' | 'open' | 'closed'

export type ApplicationStage =
  | 'applied'
  | 'screened'
  | 'interview'
  | 'offer'
  | 'hired'
  | 'rejected'

export interface JobItem {
  id: string
  title: string
  department: string
  location: string
  description: string
  required_skills: string[]
  nice_to_have_skills: string[]
  min_years: number | null
  max_years: number | null
  status: JobStatus
  created_by: string | null
  created_at: string
  updated_at: string
  application_count: number
  stage_counts: Record<string, number>
}

export interface JobPayload {
  title: string
  department: string
  location: string
  description: string
  required_skills: string[]
  nice_to_have_skills: string[]
  min_years: number | null
  max_years: number | null
  status: JobStatus
}

export interface ApplicationCardCandidate {
  id: string
  full_name: string
  email: string | null
  city: string | null
  primary_domain: string
  years_experience: number
  technical_skills: string[]
  notice_period_days?: number | null
}

export interface ApplicationItem {
  id: string
  candidate_id: string
  job_id: string
  stage: ApplicationStage
  stage_changed_at: string
  rejection_reason: string | null
  created_at: string
  updated_at: string
  candidate?: ApplicationCardCandidate | null
  job_title?: string | null
  job_department?: string | null
  job_status?: JobStatus | null
}

export interface JobDetail extends JobItem {
  applications: ApplicationItem[]
}

export interface CandidateNote {
  id: string
  candidate_id: string
  author_id: string | null
  author_name: string | null
  author_email: string | null
  body: string
  tags: string[]
  created_at: string
  updated_at: string
}

export interface ActivityTimelineItem {
  id: string
  kind: 'stage_change' | 'note' | 'audit' | string
  action: string
  summary: string
  actor_name: string | null
  actor_email: string | null
  metadata: Record<string, unknown>
  timestamp: string
}

export interface SkillNormalization {
  id: string
  canonical_name: string
  aliases: string[]
  created_at: string
  updated_at: string
}

export interface CandidateSearchItem extends CandidateListItem {
  tools?: string[]
  relevance_score?: number
  fts_score?: number
  trgm_score?: number
  semantic_score?: number
}

export interface CandidateSearchResponse {
  items: CandidateSearchItem[]
  total: number
  page: number
  page_size: number
  pages: number
  semantic_enabled: boolean
  semantic_used: boolean
  normalized_skills_filter: string[]
}

export interface JobMatchBreakdown {
  weights: {
    must_have: number
    experience_fit: number
    nice_to_have: number
    semantic: number
  }
  must_have_score: number
  matched_required_skills: string[]
  missing_required_skills: string[]
  experience_score: number
  candidate_years: number
  job_min_years: number | null
  job_max_years: number | null
  nice_to_have_score: number
  matched_nice_skills: string[]
  missing_nice_skills: string[]
  semantic_score: number
  semantic_mode: 'embedding' | 'lexical_fallback' | string
}

export interface JobMatchCandidateSummary {
  id: string
  full_name: string
  email: string | null
  city: string | null
  primary_domain: string
  years_experience: number
  technical_skills: string[]
  tools: string[]
  notice_period_days?: number | null
}

export interface JobMatchItem {
  id: string
  job_id: string
  candidate_id: string
  score: number
  breakdown: JobMatchBreakdown
  explanation: string | null
  model_version: string | null
  computed_at: string
  in_pipeline: boolean
  application_stage: ApplicationStage | null
  candidate?: JobMatchCandidateSummary | null
}

export interface CandidateCompareResponse {
  candidates: CandidateResponse[]
  shared_skills: string[]
  job_matches: Record<string, JobMatchItem>
}
