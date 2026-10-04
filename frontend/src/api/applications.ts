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

export interface ReviewData {
  dimensions: Record<string, number>
  overall: string
  hire_impression: string
  highlights: string[]
  weaknesses: string[]
  per_question: { question: string; answer_summary: string; evaluation: string; score: number }[]
  advice: string[]
  model_name?: string
  generated_at?: string
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
  review: ReviewData | null
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

/** 打断：停止当前面试官生成（已流出部分落库）。 */
export const cancelTurn = (id: number) =>
  apiFetch<{ ok: boolean; interrupted: boolean }>(`/api/applications/${id}/turns/cancel`, {
    method: 'POST',
  })

/** 面试后复盘：维度评估 + 逐题复盘（幂等，force 重生成）。 */
export const generateReview = (id: number, force = false) =>
  apiFetch<{ review: ReviewData; reused: boolean }>(`/api/applications/${id}/review`, {
    method: 'POST',
    body: JSON.stringify({ force }),
  })

// ---- 基础笔试（§5.3①）----

export interface QuizQuestion {
  id: number
  seq: number
  type: 'single' | 'multi' | 'short_answer'
  difficulty: number
  stem: string
  options: string[]
  score_full: number
  knowledge_tag: string
  reference_answer?: (number | string)[]
  scoring_points?: string[]
  my_answer?: { content: unknown; score: number; judge: { reason?: string; correct?: boolean } }
}

export interface QuizPaper {
  questions: QuizQuestion[]
  total_full: number
  total_score: number | null
  quiz_weak?: string[]
  reused?: boolean
}

export const getQuiz = (id: number) => apiFetch<QuizPaper>(`/api/applications/${id}/quiz`)

export const generateQuiz = (id: number, force = false) =>
  apiFetch<QuizPaper>(`/api/applications/${id}/quiz`, {
    method: 'POST',
    body: JSON.stringify({ force }),
  })

export const submitQuiz = (id: number, answers: { question_id: number; content: unknown }[]) =>
  apiFetch<QuizPaper>(`/api/applications/${id}/quiz/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  })

// ---- 代码笔试（§5.3②）----

export interface CodingQuestion {
  id: number
  seq: number
  stem: string
  function_signature: string
  examples: { input: string; output: string; note: string }[]
  constraints: string
  language_hint: string
  score_full: number
  my_answer?: {
    code: string
    language: string
    score: number
    judge: {
      correctness?: { score: number; comment: string }
      edge_cases?: { score: number; comment: string }
      complexity?: { score: number; comment: string }
      style?: { score: number; comment: string }
      strengths?: string[]
      weaknesses?: string[]
      summary?: string
      solution?: { approach: string; code: string; explanation: string }
      reason?: string
    }
  }
}

export interface CodingPaper {
  questions: CodingQuestion[]
  total_full: number
  total_score: number | null
  reused?: boolean
}

export const getCoding = (id: number) => apiFetch<CodingPaper>(`/api/applications/${id}/coding`)

export const generateCoding = (id: number, force = false) =>
  apiFetch<CodingPaper>(`/api/applications/${id}/coding`, {
    method: 'POST',
    body: JSON.stringify({ force }),
  })

export const submitCoding = (
  id: number,
  answers: { question_id: number; code: string; language: string }[],
) =>
  apiFetch<CodingPaper>(`/api/applications/${id}/coding/submit`, {
    method: 'POST',
    body: JSON.stringify({ answers }),
  })
