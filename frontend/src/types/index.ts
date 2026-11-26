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
  consent_given_at?: string | null
  source?: string
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
  ocr_used?: boolean
  message: string
}

export interface ParseJobItem {
  id: string
  batch_id: string
  resume_file_id: string | null
  original_filename: string
  status: 'queued' | 'processing' | 'done' | 'failed' | string
  result_json: ParsedResumeData | null
  duplicate_json: DuplicateInfo | null
  error_message: string | null
  ocr_used: boolean
  created_at: string
  updated_at: string
  completed_at: string | null
}

export interface BulkUploadResponse {
  batch_id: string
  jobs: ParseJobItem[]
  queue_backend: string
  message: string
}

export interface PrivacySettings {
  retention_days: number
  orphan_max_age_hours: number
  ocr_fallback_enabled: boolean
  semantic_search_enabled: boolean
  expired_candidates_count: number
}

export interface RetentionPurgeResponse {
  retention_days: number
  dry_run: boolean
  matched_count: number
  purged_count: number
  candidate_ids: string[]
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
  source?: string
  consent_given_at?: string | null
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
  consent_given_at?: string | null
  source?: string
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
  scorecard_count?: number
  scorecard_average?: number | null
  scorecard_recommendations?: Record<string, number>
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

export interface AdjacentSkill {
  required_skill: string
  candidate_skill: string
  relation: string
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
  adjacent_skills?: AdjacentSkill[]
  experience_score: number
  candidate_years: number
  job_min_years: number | null
  job_max_years: number | null
  nice_to_have_score: number
  matched_nice_skills: string[]
  missing_nice_skills: string[]
  semantic_score: number
  semantic_mode: 'embedding' | 'lexical_fallback' | string
  why?: string
}

export interface ConsistencyCheckItem {
  code: string
  severity: 'info' | 'check'
  message: string
  evidence: Record<string, unknown>
}

export interface CandidateBrief {
  candidate_id: string
  summary: string
  strengths: string[]
  verify_items: ConsistencyCheckItem[]
  model: string
  source_hash: string
  generated_at: string
  cached: boolean
}

export interface TimelineRole {
  index: number
  company: string
  job_title: string
  raw_start: string | null
  raw_end: string | null
  start_ym: string | null
  end_ym: string | null
  start_month_index: number | null
  end_month_index: number | null
  duration_months: number | null
  is_current: boolean
  has_invalid_dates: boolean
}

export interface TimelineGap {
  from_ym: string
  to_ym: string
  duration_months: number
  between_roles: string[]
}

export interface TimelineOverlap {
  from_ym: string
  to_ym: string
  overlap_months: number
  roles: string[]
}

export interface TenureStats {
  total_years: number
  total_months: number
  role_count: number
  dated_role_count: number
  average_tenure_months: number
  jobs_last_5_years: number
  short_stints_count: number
}

export interface CandidateTimeline {
  candidate_id: string
  gap_threshold_months: number
  roles: TimelineRole[]
  gaps: TimelineGap[]
  overlaps: TimelineOverlap[]
  tenure_stats: TenureStats
  consistency_checks: ConsistencyCheckItem[]
}

export interface InterviewParticipant {
  user_id: string
  full_name: string
  email: string
  role: string
}

export interface ScorecardAggregate {
  count: number
  average_rating: number | null
  scale: number
  recommendations: Record<string, number>
}

export interface InterviewItem {
  id: string
  application_id: string
  candidate_id: string | null
  candidate_name: string | null
  job_id: string | null
  job_title: string | null
  round_name: string
  scheduled_at: string
  duration_minutes: number
  mode: 'video' | 'phone' | 'onsite' | string
  location_or_link: string
  status: 'scheduled' | 'completed' | 'cancelled' | 'no_show' | string
  created_by: string | null
  created_at: string
  updated_at: string
  participants: InterviewParticipant[]
  scorecard_aggregate: ScorecardAggregate
}

export interface ScorecardCompetency {
  name: string
  description: string
  weight: number
}

export interface ScorecardTemplate {
  id: string
  name: string
  competencies: ScorecardCompetency[]
  scale: number
  created_at: string
  updated_at: string
}

export interface ScorecardItem {
  id: string
  interview_id: string
  interviewer_id: string
  interviewer_name: string | null
  interviewer_email: string | null
  template_id: string | null
  ratings: Record<string, number>
  average_rating: number | null
  recommendation: 'strong_no' | 'no' | 'yes' | 'strong_yes' | string
  comments: string
  submitted_at: string
}

export interface InterviewScorecards {
  interview_id: string
  aggregate: ScorecardAggregate
  scorecards: ScorecardItem[]
  peer_scorecards_locked: boolean
  viewer_aggregate_only: boolean
  my_submitted: boolean
}

export interface EmailTemplate {
  id: string
  key: string
  subject: string
  body: string
  stage_trigger: string | null
  auto_send: boolean
  created_at: string
  updated_at: string
}

export interface EmailPreview {
  to: string | null
  subject: string
  body: string
  template_key: string | null
}

export interface EmailLogItem {
  id: string
  candidate_id: string
  application_id: string | null
  template_key: string | null
  to: string
  subject: string
  status: 'queued' | 'sent' | 'failed' | string
  error: string | null
  created_by: string | null
  actor_name: string | null
  created_at: string
}

export interface OfferItem {
  id: string
  application_id: string
  candidate_id: string | null
  candidate_name: string | null
  job_id: string | null
  job_title: string | null
  offered_ctc: number
  currency: string
  status: 'draft' | 'extended' | 'accepted' | 'declined' | 'withdrawn' | string
  expected_joining_date: string | null
  decline_reason: string | null
  notes: string
  created_by: string | null
  created_at: string
  updated_at: string
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

// --- Phase 6: Hiring Analytics ---

export interface FunnelStageMetric {
  stage: string
  reached_count: number
  current_count: number
  conversion_from_previous_pct: number | null
  conversion_from_applied_pct: number | null
}

export interface FunnelAnalytics {
  total_applications: number
  active_applications: number
  hired_count: number
  rejected_count: number
  overall_hire_rate_pct: number
  stages: FunnelStageMetric[]
}

export interface TimeInStageMetric {
  stage: string
  avg_days: number | null
  median_days: number | null
  min_days: number | null
  max_days: number | null
  sample_count: number
}

export interface TimeInStageAnalytics {
  stages: TimeInStageMetric[]
}

export interface TimeToHireAnalytics {
  hired_count: number
  avg_days: number | null
  median_days: number | null
  min_days: number | null
  max_days: number | null
}

export interface SourceMetric {
  source: string
  candidates_count: number
  applications_count: number
  screened_count: number
  interview_count: number
  hired_count: number
  hire_rate_pct: number
}

export interface SourcesAnalytics {
  total_candidates: number
  sources: SourceMetric[]
}

export interface StuckCandidateItem {
  application_id: string
  candidate_id: string
  candidate_name: string
  job_id: string
  job_title: string
  stage: string
  days_in_stage: number
  threshold_days: number
  stage_changed_at: string
}

export interface StuckCandidatesAnalytics {
  thresholds: Record<string, number>
  total_stuck: number
  items: StuckCandidateItem[]
}
