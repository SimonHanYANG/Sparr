import { apiFetch } from './client'

export interface Portrait {
  skill_vector: Record<string, number>
  project_tags: string[]
  experience_level: string
  strengths: string[]
  direction_scores: Record<string, number>
}

export interface Recommendation {
  id: number
  job: { id: number; title: string; category: string; level: string; description: string }
  score: number
  matched_skills: { skill: string; weight: number; level: number }[]
  gap_skills: { skill: string; weight: number; required: boolean }[]
  reasons: string[]
}

export interface ProfilingResult {
  portrait: Portrait
  resume_version_id: number
  computed_at: string
  recommendations: Recommendation[]
}

export interface JobPosition {
  id: number
  category: string
  title: string
  level: string
  description: string
  skill_requirements: { skill: string; weight: number; required: boolean }[]
  affinity_tags: string[]
  knowledge_points: string[]
  coding_topics: string[]
  interview_focus: string[]
}

export const computePortrait = (resume_id?: number) =>
  apiFetch<ProfilingResult>('/api/profiling/compute', {
    method: 'POST',
    body: JSON.stringify(resume_id ? { resume_id } : {}),
  })

export const getPortrait = (resume_id?: number) =>
  apiFetch<ProfilingResult>(
    `/api/profiling/portrait${resume_id ? `?resume_id=${resume_id}` : ''}`,
  )

export const listJobs = (category?: string) =>
  apiFetch<JobPosition[]>(`/api/jobs${category ? `?category=${encodeURIComponent(category)}` : ''}`)
