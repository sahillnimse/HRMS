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
}

export interface ParsedResumeData extends CandidateProfileData {
  raw_parsed_data: Record<string, unknown>
}

export interface DuplicateInfo {
  is_duplicate: boolean
  candidate_id: string | null
  matched_field: string | null
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
  created_at: string
  current_title?: string | null
  current_company?: string | null
}

export interface CandidateResponse extends ParsedResumeData {
  id: string
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
  raw_parsed_data?: Record<string, unknown>
}
