/** Application session APIs — mock interview (PLAN.md §5.3③). */
import { apiFetch, apiStream } from './client'

export interface InterviewTurn {
  seq: number
  role: 'interviewer' | 'candidate' | 'system'
  content: string
  meta: Record<string, unknown>
  has_eval: boolean
  created_at: string
}

export interface PlanQuestion {
  id: string
  topic: string
  difficulty: number
  why: string
  followups: string[]
}

export interface PlanPhase {
  name: string
  target_min: number
  question_pool?: PlanQuestion[]
  targets?: { project: string; angles: string[] }[]
}

export interface PlanJson {
  briefing?: {
    persona?: string
    projects?: {
      project: string
      attack_angles?: string[]
      metrics_to_verify?: string[]
      clues?: string[]
    }[]
    self_check_weak?: string[]
    quiz_weak?: string[]
  }
  phases: PlanPhase[]
}

export interface ApplicationListItem {
  id: number
  status: 'created' | 'in_progress' | 'finished'
  current_stage: string
  job_title: string
  job: { id: number; title: string } | null
  job_profile: { id: number; title: string } | null
  last_turn_seq: number
  has_plan: boolean
  updated_at: string
  created_at: string
}

export interface ApplicationDetail {
  id: number
  status: 'created' | 'in_progress' | 'finished'
  current_stage: string
  settings: { duration_min?: number; strict_mode?: boolean }
  job: { id: number; title: string; level: string } | null
  job_profile: { id: number; title: string } | null
  job_title: string
  model_name: string
  interview_state: {
    phase?: string | null
    time_used_min?: number
    found_flaws?: { text: string; seq: number }[]
    found_highlights?: { text: string; seq: number }[]
  }
  last_turn_seq: number
  has_plan: boolean
  plan: PlanJson | null
  plan_model: string
  turns: InterviewTurn[]
  started_at: string | null
  finished_at: string | null
  updated_at: string
  created_at: string
}

export const listApplications = () =>
  apiFetch<ApplicationListItem[]>('/api/applications')

export const createApplication = (body: {
  job_id?: number
  job_profile_id?: number
  duration_min?: number
  strict_mode?: boolean
}) =>
  apiFetch<ApplicationDetail>('/api/applications', {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const getApplication = (id: number) =>
  apiFetch<ApplicationDetail>(`/api/applications/${id}`)

export const generatePlan = (id: number, force = false) =>
  apiFetch<{ plan: PlanJson; reused: boolean; model_name: string }>(
    `/api/applications/${id}/plan`,
    { method: 'POST', body: JSON.stringify({ force }) },
  )

/** SSE plan generation: stage/tick (live question reveal) then done. */
export const planStream = (
  id: number,
  onEvent: (event: string, data: Record<string, unknown>) => void,
) => apiStream(`/api/applications/${id}/plan/stream`, {}, onEvent)

export const postTurn = (
  id: number,
  body: { content?: string; action?: 'start' | 'answer' | 'hint' | 'skip' | 'end' },
  onEvent: (event: string, data: Record<string, unknown>) => void,
) => apiStream(`/api/applications/${id}/turns`, body, onEvent)
