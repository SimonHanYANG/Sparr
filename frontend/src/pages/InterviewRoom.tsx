import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import {
  cancelTurn,
  generateReview,
  getApplication,
  getCoding,
  getQuiz,
  getReport,
  planStream,
  postTurn,
  type InterviewTurn,
  type PlanJson,
  type ReviewData,
} from '../api/applications'
import CodingStage from '../components/CodingStage'
import QuizStage from '../components/QuizStage'
import ReportSection from '../components/ReportSection'

const REVIEW_DIMS = ['基础知识', '项目深度', '沟通表达', '岗位匹配']

/** Post-interview review (复盘): dimension scores + per-question timeline. */
function ReviewSection({ sessionId, review }: { sessionId: number; review: ReviewData | null }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [elapsed, setElapsed] = useState(0)
  const gen = useMutation({
    mutationFn: () => generateReview(sessionId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['application', sessionId] }),
  })
  useEffect(() => {
    if (!gen.isPending) return
    const timer = window.setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => window.clearInterval(timer)
  }, [gen.isPending])

  if (gen.isPending)
    return (
      <div className="mt-6">
        <div className="orbit-wrap">
          <div className="rounded-2xl border border-line px-6 py-7">
            <p className="text-[13.5px] font-medium text-ink">{t('interview.reviewLoading')}</p>
            <p className="mt-1 text-[11.5px] text-faint">
              {t('interview.planElapsed', { sec: elapsed })}
            </p>
            <div className="mt-4 h-0.5 w-full overflow-hidden rounded-full bg-surface">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-accent/40" />
            </div>
          </div>
        </div>
      </div>
    )

  if (!review)
    return (
      <div className="mt-6 rounded-2xl border border-line px-6 py-6 text-center">
        <p className="text-[13.5px] text-ink">{t('interview.finished')}</p>
        <p className="mt-1 text-[12px] text-muted">{t('interview.reviewHint')}</p>
        {gen.isError && <p className="mt-2 text-[12px] text-red-600">{t('interview.reviewError')}</p>}
        <button
          onClick={() => gen.mutate()}
          className="mt-4 rounded-full bg-accent px-6 py-2.5 text-[13px] font-medium text-white hover:bg-accent-hover"
        >
          {t('interview.reviewBtn')}
        </button>
      </div>
    )

  return (
    <div className="mt-6 rounded-2xl border border-line px-6 py-5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <p className="text-[15px] font-medium text-ink">{t('interview.reviewTitle')}</p>
        <span
          className={`rounded-full px-2.5 py-0.5 text-[11px] ${
            review.hire_impression === '强推' || review.hire_impression === '推荐'
              ? 'bg-emerald-50 text-emerald-700'
              : review.hire_impression === '不推荐'
                ? 'bg-red-50 text-red-600'
                : 'bg-amber-50 text-amber-700'
          }`}
        >
          {t(`interview.hire.${review.hire_impression}`)}
        </span>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-ink">{review.overall}</p>

      {/* dimension bars */}
      <p className="mt-4 text-[11.5px] font-medium text-muted">{t('interview.reviewDims')}</p>
      <div className="mt-2 space-y-1.5">
        {REVIEW_DIMS.filter((d) => review.dimensions[d] != null).map((d) => (
          <div key={d} className="flex items-center gap-3">
            <span className="w-16 shrink-0 text-[11.5px] text-muted">
              {t(`interview.dims.${d}`)}
            </span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
              <div
                className="h-full rounded-full bg-accent/70"
                style={{ width: `${review.dimensions[d]}%` }}
              />
            </div>
            <span className="w-8 shrink-0 text-right text-[11.5px] tabular-nums text-ink">
              {review.dimensions[d]}
            </span>
          </div>
        ))}
      </div>

      {review.highlights.length > 0 && (
        <>
          <p className="mt-4 text-[11.5px] font-medium text-emerald-700">
            {t('interview.reviewHighlights')}
          </p>
          <ul className="mt-1.5 space-y-1">
            {review.highlights.map((h, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-muted">
                · {h}
              </li>
            ))}
          </ul>
        </>
      )}
      {review.weaknesses.length > 0 && (
        <>
          <p className="mt-3 text-[11.5px] font-medium text-amber-700">
            {t('interview.reviewWeaknesses')}
          </p>
          <ul className="mt-1.5 space-y-1">
            {review.weaknesses.map((w, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-muted">
                · {w}
              </li>
            ))}
          </ul>
        </>
      )}

      {review.per_question.length > 0 && (
        <>
          <p className="mt-4 text-[11.5px] font-medium text-muted">
            {t('interview.reviewPerQuestion')}
          </p>
          <div className="mt-2 space-y-2">
            {review.per_question.map((q, i) => (
              <div key={i} className="rounded-xl bg-surface px-4 py-2.5">
                <div className="flex items-start gap-2">
                  <p className="min-w-0 flex-1 text-[12px] font-medium text-ink">{q.question}</p>
                  <span className="shrink-0 text-[11px] tabular-nums text-accent">
                    {q.score}/5
                  </span>
                </div>
                <p className="mt-1 text-[11px] text-faint">{q.answer_summary}</p>
                <p className="mt-0.5 text-[11.5px] leading-relaxed text-muted">{q.evaluation}</p>
              </div>
            ))}
          </div>
        </>
      )}

      {review.advice.length > 0 && (
        <>
          <p className="mt-4 text-[11.5px] font-medium text-muted">{t('interview.reviewAdvice')}</p>
          <ul className="mt-1.5 space-y-1">
            {review.advice.map((a, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-muted">
                · {a}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

/** Plan preview: phases + per-question why (anti-mechanical transparency). */
function PlanCard({ plan }: { plan: PlanJson }) {
  const { t } = useTranslation()
  return (
    <div className="rounded-2xl border border-line px-6 py-5">
      <p className="text-[13px] font-medium text-ink">{t('interview.planTitle')}</p>
      {plan.briefing?.persona && (
        <p className="mt-1.5 text-[12px] text-muted">{plan.briefing.persona}</p>
      )}
      {plan.briefing?.self_check_weak && plan.briefing.self_check_weak.length > 0 && (
        <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-[11.5px] text-amber-700">
          ★ {t('interview.weakTitle')}：{plan.briefing.self_check_weak.join('、')}
        </p>
      )}
      <div className="mt-3 space-y-2">
        {plan.phases.map((phase, i) => (
          <div key={i} className="rounded-xl bg-surface px-4 py-2.5">
            <p className="text-[12.5px] font-medium text-ink">
              {i + 1}. {phase.name}
              <span className="ml-2 text-[11px] font-normal text-faint">
                {phase.target_min} {t('interview.minutes')}
              </span>
            </p>
            {(phase.question_pool ?? []).slice(0, 2).map((q) => (
              <p key={q.id} className="mt-1 text-[11.5px] leading-relaxed text-muted">
                · {q.topic}
                <span className="text-faint"> — {q.why}</span>
              </p>
            ))}
            {(phase.targets ?? []).map((tg, j) => (
              <p key={j} className="mt-1 text-[11.5px] text-muted">
                · {t('interview.projectDig')}「{tg.project}」
              </p>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

function TurnBubble({ turn }: { turn: InterviewTurn }) {
  const { t } = useTranslation()
  if (!turn.content.trim()) return null // 空轮次（如打断残留）不渲染
  if (turn.role === 'system')
    return <p className="my-3 text-center text-[11px] text-faint">{turn.content}</p>
  const mine = turn.role === 'candidate'
  return (
    <div className={`mb-4 flex ${mine ? 'justify-end' : 'justify-start'}`}>
      <div className="max-w-[85%]">
        <p className={`mb-1 text-[10.5px] text-faint ${mine ? 'text-right' : ''}`}>
          {mine ? t('interview.you') : t('interview.interviewer')}
        </p>
        <div
          className={`whitespace-pre-wrap rounded-2xl px-4 py-3 text-[13.5px] leading-relaxed ${
            mine ? 'bg-accent/10 text-ink' : 'border border-line bg-white text-ink'
          }`}
        >
          {turn.content}
        </div>
      </div>
    </div>
  )
}

/** Plan generation loading card: orbiting light ring + live question reveal. */
function PlanLoader({ sessionId, onDone }: { sessionId: number; onDone: () => void }) {
  const { t } = useTranslation()
  const [hints, setHints] = useState<string[]>([])
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const started = useRef(false)

  const run = () => {
    setError('')
    setHints([])
    setElapsed(0)
    planStream(sessionId, (event, data) => {
      if (event === 'tick') setHints(((data.items as string[]) ?? []).slice(0, 10))
      else if (event === 'done') onDone()
      else if (event === 'error') setError((data.detail as string) || t('interview.planError'))
    }).catch(() => setError(t('interview.planError')))
  }

  useEffect(() => {
    // auto-run once (guard against StrictMode double-mount)…
    if (!started.current) {
      started.current = true
      run()
    }
    // …but the elapsed timer must survive remounts (cleanup would kill it)
    const timer = window.setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="mt-6">
      <div className="orbit-wrap">
        <div className="rounded-2xl border border-line px-6 py-7">
          <p className="text-[13.5px] font-medium text-ink">{t('interview.planBuilding')}</p>
          <p className="mt-1 text-[11.5px] text-faint">
            {t('interview.planElapsed', { sec: elapsed })}
          </p>
          {hints.length > 0 ? (
            <ul className="mt-3 space-y-1">
              {hints.map((h) => (
                <li key={h} className="text-[11.5px] text-muted">
                  · {t('interview.planLive')}
                  {h}
                </li>
              ))}
            </ul>
          ) : (
            !error && (
              <p className="mt-3 text-[11.5px] text-faint">{t('interview.planWarmup')}</p>
            )
          )}
          {error ? (
            <>
              <p className="mt-3 text-[12px] text-red-600">{error}</p>
              <button
                onClick={run}
                className="mt-3 rounded-full border border-line px-5 py-2 text-[12.5px] text-ink transition-colors hover:border-accent hover:text-accent"
              >
                {t('interview.planRetry')}
              </button>
            </>
          ) : (
            <div className="mt-4 h-0.5 w-full overflow-hidden rounded-full bg-surface">
              <div className="h-full w-1/3 animate-pulse rounded-full bg-accent/40" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** SSE interview room — transcript, streaming reply, controls, 断点续面. */
export default function InterviewRoom() {
  const { t } = useTranslation()
  const { id } = useParams()
  const sessionId = Number(id)
  const queryClient = useQueryClient()
  const [input, setInput] = useState('')
  const [streamingText, setStreamingText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // 乐观上屏：发言立刻渲染，不等服务端落库回包（seq 与服务端对齐以便去重）
  const [pending, setPending] = useState<InterviewTurn[]>([])
  const [tab, setTab] = useState<'quiz' | 'coding' | 'interview' | 'report' | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: session } = useQuery({
    queryKey: ['application', sessionId],
    queryFn: () => getApplication(sessionId),
    enabled: Number.isFinite(sessionId),
  })
  // 阶段完成状态（与阶段组件共享查询缓存）
  const { data: quizInfo } = useQuery({
    queryKey: ['quiz', sessionId],
    queryFn: () => getQuiz(sessionId),
    enabled: Number.isFinite(sessionId),
  })
  const { data: codingInfo } = useQuery({
    queryKey: ['coding', sessionId],
    queryFn: () => getCoding(sessionId),
    enabled: Number.isFinite(sessionId),
  })
  // 报告查询（hooks 必须在条件早退之前声明）
  const { data: reportInfo } = useQuery({
    queryKey: ['report', sessionId],
    queryFn: () => getReport(sessionId),
    enabled: Number.isFinite(sessionId),
  })

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [session?.turns?.length, streamingText])

  const send = (body: { content?: string; action?: 'start' | 'answer' | 'hint' | 'skip' | 'end' }) => {
    if (busy) return
    setBusy(true)
    setError('')
    setStreamingText('')
    const action = body.action ?? 'answer'
    const seq = (session?.last_turn_seq ?? 0) + 1
    const labels: Record<string, string> = {
      start: t('interview.sysStart'),
      hint: `（${t('interview.hint')}）`,
      skip: `（${t('interview.skip')}）`,
      end: `（${t('interview.end')}）`,
    }
    setPending((prev) => [
      ...prev,
      {
        seq,
        role: action === 'answer' ? 'candidate' : 'system',
        content: action === 'answer' ? (body.content ?? '') : labels[action],
        meta: { action },
        has_eval: false,
        created_at: new Date().toISOString(),
      },
    ])
    if (action === 'answer') setInput('')
    const refresh = () =>
      queryClient
        .invalidateQueries({ queryKey: ['application', sessionId] })
        .finally(() => setPending([]))
    postTurn(sessionId, body, (event, data) => {
      if (event === 'delta') {
        setStreamingText((prev) => prev + (data.text as string))
      } else if (event === 'done') {
        setStreamingText('')
        void refresh()
      } else if (event === 'error') {
        setError((data.detail as string) || t('interview.turnError'))
        setStreamingText('')
        void refresh()
      }
    })
      .catch(() => {
        setError(t('interview.turnError'))
        void refresh()
      })
      .finally(() => setBusy(false))
  }

  if (!session) return <div className="pt-16 text-center text-muted">{t('common.loading')}</div>

  const turns = session.turns ?? []
  const finished = session.status === 'finished'
  // 服务端转录 + 尚未落库回包的乐观消息（按 seq 去重合并；普通计算，避开条件早退后的 hooks 问题）
  const knownSeqs = new Set(turns.map((t) => t.seq))
  const shownTurns = [...turns, ...pending.filter((p) => !knownSeqs.has(p.seq))].sort(
    (a, b) => a.seq - b.seq,
  )
  const started = shownTurns.length > 0

  // 三段式 + 总结报告：默认落在第一个未完成的阶段（也允许自由切换/重考）；结束进总结
  const quizDone = quizInfo?.total_score != null
  const codingDone = codingInfo?.total_score != null
  const interviewDone = session.status === 'finished'
  const reportDone = reportInfo?.report != null
  const autoTab: 'quiz' | 'coding' | 'interview' | 'report' = !quizDone
    ? 'quiz'
    : !codingDone
      ? 'coding'
      : !interviewDone
        ? 'interview'
        : 'report'
  const activeTab = tab ?? autoTab

  return (
    <div className="mx-auto max-w-5xl pt-6">
      {/* header */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h1 className="text-[20px] font-semibold tracking-tight text-ink">{session.job_title}</h1>
        <span className="rounded-full bg-surface px-2.5 py-0.5 text-[11px] text-muted">
          {t(`interview.status.${session.status}`)}
        </span>
        {session.interview_state?.phase != null && (
          <span className="text-[11px] text-faint">
            {t('interview.phase')}: {String(session.interview_state.phase)}
          </span>
        )}
      </div>
      <Link to="/applications" className="mt-1 inline-block text-[11.5px] text-faint hover:text-ink">
        ← {t('interview.backToList')}
      </Link>

      {/* 三段式 + 总结报告阶段条：宽松跳转，完成打勾 */}
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {(['quiz', 'coding', 'interview', 'report'] as const).map((k, i) => {
          const done =
            k === 'quiz' ? quizDone : k === 'coding' ? codingDone : k === 'interview' ? interviewDone : reportDone
          return (
            <button
              key={k}
              onClick={() => setTab(k)}
              className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12px] transition-colors ${
                activeTab === k ? 'bg-ink text-white' : 'border border-line text-muted hover:text-ink'
              }`}
            >
              <span>{done ? '✓' : i + 1}</span>
              {t(`interview.stages.${k}`)}
            </button>
          )
        })}
      </div>

      {activeTab === 'quiz' && <QuizStage sessionId={sessionId} onGo={setTab} />}
      {activeTab === 'coding' && <CodingStage sessionId={sessionId} onGo={setTab} />}
      {activeTab === 'report' && <ReportSection sessionId={sessionId} />}
      {activeTab === 'interview' && (
        <>

      {/* plan gate — auto-generates with live progress (orbit loading card) */}
      {!session.has_plan && (
        <PlanLoader
          sessionId={sessionId}
          onDone={() =>
            void queryClient.invalidateQueries({ queryKey: ['application', sessionId] })
          }
        />
      )}

      {/* plan preview before start / resume banner after */}
      {session.has_plan && session.plan && !started && (
        <div className="mx-auto mt-5 max-w-4xl">
          <PlanCard plan={session.plan} />
          <button
            onClick={() => send({ action: 'start' })}
            disabled={busy}
            className="mt-5 w-full rounded-full bg-accent px-6 py-3 text-[14px] font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            {busy ? t('interview.thinking') : t('interview.start')}
          </button>
        </div>
      )}

      {started && turns.length > 0 && turns.length <= 2 && !finished && (
        <p className="mx-auto mt-4 max-w-4xl rounded-xl bg-surface px-4 py-2.5 text-[11.5px] text-muted">
          {t('interview.resumeBanner')}
        </p>
      )}

      {/* transcript */}
      {started && (
        <div className="mx-auto mt-5 max-w-4xl">
          {shownTurns.map((turn) => (
            <TurnBubble key={turn.seq} turn={turn} />
          ))}
          {/* 面试官思考中：等首个字期间的三点气泡，字一流出来就让位 */}
          {busy && !streamingText && (
            <div className="mb-4 flex justify-start">
              <div className="max-w-[85%]">
                <p className="mb-1 text-[10.5px] text-faint">{t('interview.interviewer')}</p>
                <div
                  className="flex items-center gap-1.5 rounded-2xl border border-line bg-white px-4 py-3.5"
                  role="status"
                  aria-label={t('interview.thinking')}
                >
                  <span className="typing-dot h-1.5 w-1.5 rounded-full bg-muted" />
                  <span className="typing-dot h-1.5 w-1.5 rounded-full bg-muted" />
                  <span className="typing-dot h-1.5 w-1.5 rounded-full bg-muted" />
                </div>
              </div>
            </div>
          )}
          {streamingText && (
            <div className="mb-4 flex justify-start">
              <div className="max-w-[85%]">
                <p className="mb-1 text-[10.5px] text-faint">{t('interview.interviewer')}</p>
                <div className="whitespace-pre-wrap rounded-2xl border border-line bg-white px-4 py-3 text-[13.5px] leading-relaxed text-ink">
                  {streamingText}
                  <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-accent align-middle" />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>
      )}

      {error && <p className="mx-auto mt-3 max-w-4xl text-[12px] text-red-600">{error}</p>}

      {/* input + controls */}
      {session.has_plan && started && !finished && (
        <div className="mx-auto mt-4 max-w-4xl">
          <div className="flex flex-wrap gap-2">
            {busy ? (
              /* 打断：随时打断面试官的输出（已流出部分保留） */
              <button
                onClick={() => void cancelTurn(sessionId)}
                className="rounded-full border border-accent px-4 py-1.5 text-[12px] font-medium text-accent transition-colors hover:bg-accent/10"
              >
                ⏹ {t('interview.interrupt')}
              </button>
            ) : (
              <>
                <button
                  onClick={() => send({ action: 'hint' })}
                  className="rounded-full border border-line px-3.5 py-1.5 text-[12px] text-muted hover:border-accent hover:text-accent"
                >
                  {t('interview.hint')}
                </button>
                <button
                  onClick={() => send({ action: 'skip' })}
                  className="rounded-full border border-line px-3.5 py-1.5 text-[12px] text-muted hover:border-accent hover:text-accent"
                >
                  {t('interview.skip')}
                </button>
                <button
                  onClick={() => {
                    if (window.confirm(t('interview.endConfirm'))) send({ action: 'end' })
                  }}
                  className="rounded-full border border-line px-3.5 py-1.5 text-[12px] text-faint hover:border-red-300 hover:text-red-500"
                >
                  {t('interview.end')}
                </button>
              </>
            )}
          </div>
          <div className="mt-2.5 flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  if (input.trim()) send({ action: 'answer', content: input.trim() })
                }
              }}
              rows={2}
              placeholder={t('interview.inputPlaceholder')}
              className="min-h-[52px] flex-1 resize-none rounded-2xl border border-line bg-white px-4 py-3 text-[13.5px] leading-relaxed text-ink placeholder:text-faint focus:border-accent focus:outline-none"
            />
            <button
              onClick={() => input.trim() && send({ action: 'answer', content: input.trim() })}
              disabled={busy || !input.trim()}
              className="shrink-0 rounded-full bg-accent px-5 py-3 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {t('interview.send')}
            </button>
          </div>
        </div>
      )}

      {finished && (
        <>
          <ReviewSection sessionId={sessionId} review={session.review ?? null} />
          <div className="mt-4 text-center">
            <Link
              to="/applications"
              className="inline-block text-[12.5px] text-accent hover:underline"
            >
              {t('interview.backToList')} →
            </Link>
          </div>
        </>
      )}
        </>
      )}
    </div>
  )
}
