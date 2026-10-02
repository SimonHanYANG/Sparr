import { apiFetch, apiStream } from './client'

export interface Portrait {
  skill_vector: Record<string, number>
  project_tags: string[]
  experience_level: string
  strengths: string[]
  direction_scores: Record<string, number>
}

export interface MatchEval {
  id?: number
  score: number
  summary: string
  matched: { requirement: string; evidence: string }[]
  gaps: { requirement: string; status: string; advice: string }[]
  advice: string[]
  model_name?: string
  job?: { id: number; title: string; category: string; level: string; levels?: string[] } | null
  job_profile?: { id: number; title: string } | null
}

export interface ProfilingResult {
  portrait: Portrait
  resume_version_id: number
  computed_at: string
  recommendations: unknown[]
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

/** Rule-based quick signal: direction bars etc. */
export const computePortrait = (resume_id?: number) =>
  apiFetch<ProfilingResult>('/api/profiling/compute', {
    method: 'POST',
    body: JSON.stringify(resume_id ? { resume_id } : {}),
  })

/** LLM evaluations of the preset catalog — streamed progressively (SSE). */
export const analyzeCatalogStream = (
  onEval: (ev: MatchEval, progress: { done: number; total: number }) => void,
  onDone: (progress: { done: number; total: number }) => void,
  onMeta?: (meta: { total: number; candidates?: number; model?: string }) => void,
) =>
  apiStream('/api/jobs/analyze-catalog/stream', {}, (event, data) => {
    if (event === 'meta') {
      onMeta?.(data as unknown as { total: number; candidates?: number; model?: string })
    } else if (event === 'eval') {
      onEval(data as unknown as MatchEval, (data.progress as { done: number; total: number }) ?? { done: 0, total: 0 })
    } else if (event === 'done') {
      onDone({ done: (data.done as number) ?? 0, total: (data.total as number) ?? 0 })
    } else if (event === 'error') {
      throw new Error((data.detail as string) ?? 'analyze failed')
    }
  })

/** LLM analysis of one position — preset job_id or custom job_profile_id. */
export const analyzeMatch = (payload: { job_id?: number; job_profile_id?: number }) =>
  apiFetch<MatchEval>('/api/jobs/analyze', { method: 'POST', body: JSON.stringify(payload) })

export interface JobProfile {
  id: number
  title: string
  jd_text: string
  created_at: string
}

export const listJobProfiles = () => apiFetch<JobProfile[]>('/api/jobs/profiles')

export const createJobProfile = (title: string, jd_text: string) =>
  apiFetch<JobProfile>('/api/jobs/profiles', {
    method: 'POST',
    body: JSON.stringify({ title, jd_text }),
  })

export const listJobs = (category?: string) =>
  apiFetch<JobPosition[]>(`/api/jobs${category ? `?category=${encodeURIComponent(category)}` : ''}`)
