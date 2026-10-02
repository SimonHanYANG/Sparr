/** Structured resume schema — mirrors backend apps/resumes/extraction.py. */
export interface ResumeBasics {
  name: string
  intent_role: string
  contact: string
  years_exp: string
}

export interface EducationItem {
  school: string
  degree: string
  major: string
  period: string
  desc: string
}

export interface SkillItem {
  name: string
  level: string
  desc?: string
}

export interface ProjectItem {
  name: string
  role: string
  period: string
  tech_stack: string[]
  bullets: string[]
  metrics: string[]
}

export interface WorkItem {
  company: string
  role: string
  period: string
  bullets: string[]
}

export interface StructuredResume {
  basics: ResumeBasics
  education: EducationItem[]
  skills: SkillItem[]
  projects: ProjectItem[]
  work_experiences: WorkItem[]
  awards: string[]
}

export type ParseStatus = 'uploaded' | 'parsing' | 'parsed' | 'failed'

export interface VersionSummary {
  id: number
  version_no: number
  change_note: string
  created_at: string
}

export interface ResumeVersion extends VersionSummary {
  structured_json: StructuredResume
}

export interface Resume {
  id: number
  title: string
  source_filename: string
  parse_status: ParseStatus
  parse_error: string
  current_version: VersionSummary | null
  created_at: string
  updated_at: string
}

export interface ResumeDetail extends Resume {
  mineru_markdown: string
  versions: VersionSummary[]
}

export function emptyStructured(): StructuredResume {
  return {
    basics: { name: '', intent_role: '', contact: '', years_exp: '' },
    education: [],
    skills: [],
    projects: [],
    work_experiences: [],
    awards: [],
  }
}
