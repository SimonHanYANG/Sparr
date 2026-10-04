import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  generateQuiz,
  getQuiz,
  submitQuiz,
  type QuizPaper,
} from '../api/applications'

const QUIZ_TIME_MIN = 20

/** 基础笔试（§5.3①）：组卷 → 倒计时作答 → 判卷复盘（防作弊，交卷前无参考答案）。 */
export default function QuizStage({
  sessionId,
  onGo,
}: {
  sessionId: number
  onGo: (tab: 'quiz' | 'coding' | 'interview') => void
}) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [answers, setAnswers] = useState<Record<number, unknown>>({})
  const [qIndex, setQIndex] = useState(0)
  const [elapsed, setElapsed] = useState(0)
  const [secondsLeft, setSecondsLeft] = useState(QUIZ_TIME_MIN * 60)
  const submittedRef = useRef(false)

  const { data: paper } = useQuery({
    queryKey: ['quiz', sessionId],
    queryFn: () => getQuiz(sessionId),
  })

  const gen = useMutation({
    mutationFn: () => generateQuiz(sessionId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['quiz', sessionId] }),
  })
  const submit = useMutation({
    mutationFn: () =>
      submitQuiz(
        sessionId,
        Object.entries(answers).map(([qid, content]) => ({
          question_id: Number(qid),
          content,
        })),
      ),
    onSuccess: () => {
      submittedRef.current = true
      onGo('quiz') // 钉在本段展示判卷结果，不自动跳走
      void queryClient.invalidateQueries({ queryKey: ['quiz', sessionId] })
      void queryClient.invalidateQueries({ queryKey: ['application', sessionId] })
    },
  })

  // 生成/判卷中的计时器 + 答题倒计时
  useEffect(() => {
    if (gen.isPending || submit.isPending) {
      const timer = window.setInterval(() => setElapsed((e) => e + 1), 1000)
      return () => window.clearInterval(timer)
    }
    setElapsed(0)
  }, [gen.isPending, submit.isPending])

  const answering = paper && paper.total_score == null && !submit.isSuccess
  useEffect(() => {
    if (!answering) return
    const timer = window.setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1 && !submittedRef.current) {
          submittedRef.current = true
          submit.mutate()
          return 0
        }
        return s - 1
      })
    }, 1000)
    return () => window.clearInterval(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [answering])

  if (!paper || gen.isPending)
    return (
      <div className="mx-auto mt-2 max-w-3xl">
        <div className="orbit-wrap">
          <div className="rounded-2xl border border-line px-6 py-7">
            <p className="text-[13.5px] font-medium text-ink">{t('quiz.generating')}</p>
            <p className="mt-1 text-[11.5px] text-faint">{t('interview.planElapsed', { sec: elapsed })}</p>
            {!gen.isPending && <p className="mt-2 text-[12px] text-muted">{t('quiz.genHint')}</p>}
            {!gen.isPending && (
              <button
                onClick={() => gen.mutate()}
                className="mt-4 rounded-full bg-accent px-6 py-2.5 text-[13px] font-medium text-white hover:bg-accent-hover"
              >
                {t('quiz.genBtn')}
              </button>
            )}
            {gen.isPending && (
              <div className="mt-4 h-0.5 w-full overflow-hidden rounded-full bg-surface">
                <div className="h-full w-1/3 animate-pulse rounded-full bg-accent/40" />
              </div>
            )}
          </div>
        </div>
        {gen.isError && <p className="mt-2 text-[12px] text-red-600">{t('quiz.genError')}</p>}
      </div>
    )

  if (paper.questions.length === 0)
    return (
      <div className="mt-2 rounded-2xl border border-line px-6 py-8 text-center">
        <button
          onClick={() => gen.mutate()}
          className="rounded-full bg-accent px-6 py-2.5 text-[13px] font-medium text-white hover:bg-accent-hover"
        >
          {t('quiz.genBtn')}
        </button>
      </div>
    )

  // 判卷结果
  if (paper.total_score != null && !submit.isPending)
    return (
      <QuizResult
        paper={paper}
        onRetry={() => {
          setAnswers({})
          submittedRef.current = false
          gen.mutate()
        }}
        onNext={() => onGo('coding')}
      />
    )

  const mm = String(Math.floor(secondsLeft / 60)).padStart(2, '0')
  const ss = String(secondsLeft % 60).padStart(2, '0')
  const total = paper.questions.length
  const q = paper.questions[Math.min(qIndex, total - 1)]
  const answeredCount = paper.questions.filter((x) => answers[x.id] !== undefined).length

  return (
    <div className="mx-auto mt-2 max-w-3xl">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12px] text-muted">
          {t('quiz.answerHint', { count: total })}
        </p>
        <span
          className={`rounded-full px-3 py-1 text-[12px] tabular-nums ${
            secondsLeft < 120 ? 'bg-red-50 text-red-600' : 'bg-surface text-ink'
          }`}
        >
          ⏱ {mm}:{ss}
        </span>
      </div>

      {/* 题号导航格：已答着色，点击跳题（单题卡片模式，页面不再无限拉长） */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {paper.questions.map((x, i) => {
          const done = answers[x.id] !== undefined
          return (
            <button
              key={x.id}
              onClick={() => setQIndex(i)}
              className={`flex h-7 w-7 items-center justify-center rounded-lg text-[11px] tabular-nums transition-colors ${
                i === qIndex
                  ? 'bg-ink text-white'
                  : done
                    ? 'bg-accent/10 text-accent'
                    : 'border border-line text-faint hover:text-ink'
              }`}
            >
              {i + 1}
            </button>
          )
        })}
      </div>

      {/* 单题卡片 */}
      <div className="mt-3 rounded-2xl border border-line px-5 py-4">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className="text-[11px] text-faint">
            {t('quiz.qNo', { cur: qIndex + 1, total })} · {t(`quiz.types.${q.type}`)} ·{' '}
            {t('quiz.difficulty')} {q.difficulty}
          </span>
          <span className="text-[10.5px] text-faint">· {q.score_full} 分</span>
        </div>
        <p className="mt-1.5 whitespace-pre-wrap text-[13px] leading-relaxed text-ink">{q.stem}</p>
        <div className="mt-2.5 space-y-1.5">
          {q.type === 'short_answer' ? (
            <textarea
              rows={5}
              value={(answers[q.id] as string) ?? ''}
              onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
              placeholder={t('quiz.shortPh')}
              className="w-full resize-none rounded-xl border border-line bg-white px-3.5 py-2.5 text-[13px] leading-relaxed text-ink placeholder:text-faint focus:border-accent focus:outline-none"
            />
          ) : (
            q.options.map((opt, oi) => {
              const single = q.type === 'single'
              const picked = single
                ? (answers[q.id] as number[] | undefined)?.[0] === oi
                : ((answers[q.id] as number[] | undefined) ?? []).includes(oi)
              return (
                <button
                  key={oi}
                  onClick={() =>
                    setAnswers((a) => {
                      if (single) return { ...a, [q.id]: [oi] }
                      const cur = (a[q.id] as number[] | undefined) ?? []
                      return {
                        ...a,
                        [q.id]: cur.includes(oi)
                          ? cur.filter((x) => x !== oi)
                          : [...cur, oi],
                      }
                    })
                  }
                  className={`flex w-full items-start gap-2.5 rounded-xl border px-3.5 py-2 text-left transition-colors ${
                    picked ? 'border-accent bg-accent/5' : 'border-line hover:border-faint'
                  }`}
                >
                  <span
                    className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center text-[10px] ${
                      picked ? 'bg-accent text-white' : 'border border-line text-transparent'
                    } ${single ? 'rounded-full' : 'rounded'}`}
                  >
                    ✓
                  </span>
                  <span className="text-[12.5px] leading-relaxed text-ink">{opt}</span>
                </button>
              )
            })
          )}
        </div>
      </div>

      {/* 翻页 */}
      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => setQIndex((i) => Math.max(0, i - 1))}
          disabled={qIndex === 0}
          className="rounded-full border border-line px-4 py-1.5 text-[12px] text-ink hover:border-accent hover:text-accent disabled:opacity-40"
        >
          ← {t('quiz.prev')}
        </button>
        <span className="flex-1 text-center text-[11px] text-faint">
          {t('quiz.progress', { answered: answeredCount, total })}
        </span>
        <button
          onClick={() => setQIndex((i) => Math.min(total - 1, i + 1))}
          disabled={qIndex >= total - 1}
          className="rounded-full border border-line px-4 py-1.5 text-[12px] text-ink hover:border-accent hover:text-accent disabled:opacity-40"
        >
          {t('quiz.next')} →
        </button>
      </div>

      {submit.isError && <p className="mt-2 text-[12px] text-red-600">{t('quiz.submitError')}</p>}
      <button
        onClick={() => {
          if (window.confirm(t('quiz.submitConfirm'))) submit.mutate()
        }}
        disabled={submit.isPending}
        className="mt-3 w-full rounded-full bg-accent px-6 py-3 text-[13.5px] font-medium text-white hover:bg-accent-hover disabled:opacity-50"
      >
        {submit.isPending ? t('quiz.grading') : t('quiz.submit')}
      </button>
    </div>
  )
}

/** 判卷结果：得分 + 逐题对错/评语/参考答案 + 薄弱考点（喂给面试官）。 */
function QuizResult({
  paper,
  onRetry,
  onNext,
}: {
  paper: QuizPaper
  onRetry: () => void
  onNext: () => void
}) {
  const { t } = useTranslation()
  return (
    <div className="mx-auto mt-2 max-w-3xl">
      <div className="rounded-2xl border border-line px-6 py-5">
        <p className="text-[15px] font-medium text-ink">
          {t('quiz.score', {
            score: Math.round(paper.total_score ?? 0),
            full: paper.total_full,
          })}
        </p>
        {paper.quiz_weak && paper.quiz_weak.length > 0 && (
          <p className="mt-2 rounded-xl bg-amber-50 px-3.5 py-2.5 text-[11.5px] leading-relaxed text-amber-700">
            ★ {t('quiz.weakNote')}：{paper.quiz_weak.join('、')}
          </p>
        )}
      </div>

      <div className="mt-3 space-y-3">
        {paper.questions.map((q, i) => {
          const ans = q.my_answer
          const ok = ans?.judge?.correct === true
          return (
            <div key={q.id} className="rounded-2xl border border-line px-5 py-4">
              <div className="flex items-start gap-2">
                <p className="min-w-0 flex-1 text-[13px] leading-relaxed text-ink">
                  {i + 1}. {q.stem}
                </p>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] tabular-nums ${
                    ok
                      ? 'bg-emerald-50 text-emerald-700'
                      : (ans?.score ?? 0) > 0
                        ? 'bg-amber-50 text-amber-700'
                        : 'bg-red-50 text-red-600'
                  }`}
                >
                  {ans?.score ?? 0}/{q.score_full}
                </span>
              </div>
              {ans?.judge?.reason && (
                <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted">{ans.judge.reason}</p>
              )}
              {q.reference_answer && (
                <div className="mt-2 rounded-xl bg-surface px-3.5 py-2.5">
                  <p className="text-[11px] font-medium text-muted">{t('quiz.reference')}</p>
                  <p className="mt-1 text-[11.5px] leading-relaxed text-ink">
                    {q.type === 'short_answer'
                      ? String(q.reference_answer[0] ?? '')
                      : (q.reference_answer as number[]).map((idx) => q.options[idx]).join('；')}
                  </p>
                  {q.scoring_points && q.scoring_points.length > 0 && (
                    <p className="mt-1.5 text-[11px] leading-relaxed text-faint">
                      {t('quiz.scoringPoints')}：{q.scoring_points.join('；')}
                    </p>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          onClick={onNext}
          className="rounded-full bg-accent px-6 py-2.5 text-[13px] font-medium text-white hover:bg-accent-hover"
        >
          {t('quiz.nextCoding')} →
        </button>
        <button
          onClick={onRetry}
          className="rounded-full border border-line px-5 py-2 text-[12.5px] text-ink hover:border-accent hover:text-accent"
        >
          {t('quiz.retry')}
        </button>
      </div>
    </div>
  )
}
