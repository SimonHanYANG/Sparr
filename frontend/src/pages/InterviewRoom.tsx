import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import {
  getApplication,
  planStream,
  postTurn,
  type InterviewTurn,
  type PlanJson,
} from '../api/applications'

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
  const bottomRef = useRef<HTMLDivElement>(null)

  const { data: session } = useQuery({
    queryKey: ['application', sessionId],
    queryFn: () => getApplication(sessionId),
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

  return (
    <div className="mx-auto max-w-2xl pt-6">
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
        <div className="mt-5">
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
        <p className="mt-4 rounded-xl bg-surface px-4 py-2.5 text-[11.5px] text-muted">
          {t('interview.resumeBanner')}
        </p>
      )}

      {/* transcript */}
      {started && (
        <div className="mt-5">
          {shownTurns.map((turn) => (
            <TurnBubble key={turn.seq} turn={turn} />
          ))}
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

      {error && <p className="mt-3 text-[12px] text-red-600">{error}</p>}

      {/* input + controls */}
      {session.has_plan && started && !finished && (
        <div className="mt-4">
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => send({ action: 'hint' })}
              disabled={busy}
              className="rounded-full border border-line px-3.5 py-1.5 text-[12px] text-muted hover:border-accent hover:text-accent disabled:opacity-50"
            >
              {t('interview.hint')}
            </button>
            <button
              onClick={() => send({ action: 'skip' })}
              disabled={busy}
              className="rounded-full border border-line px-3.5 py-1.5 text-[12px] text-muted hover:border-accent hover:text-accent disabled:opacity-50"
            >
              {t('interview.skip')}
            </button>
            <button
              onClick={() => {
                if (window.confirm(t('interview.endConfirm'))) send({ action: 'end' })
              }}
              disabled={busy}
              className="rounded-full border border-line px-3.5 py-1.5 text-[12px] text-faint hover:border-red-300 hover:text-red-500 disabled:opacity-50"
            >
              {t('interview.end')}
            </button>
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
        <div className="mt-6 rounded-2xl border border-line px-6 py-6 text-center">
          <p className="text-[14px] text-ink">{t('interview.finished')}</p>
          <Link
            to="/applications"
            className="mt-2 inline-block text-[12.5px] text-accent hover:underline"
          >
            {t('interview.backToList')} →
          </Link>
        </div>
      )}
    </div>
  )
}
