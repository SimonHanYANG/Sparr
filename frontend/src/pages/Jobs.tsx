import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import {
  analyzeMatch,
  getSelfCheck,
  listJobProfiles,
  listJobs,
  saveSelfCheck,
  toggleJobTarget,
  type JobPosition,
  type MatchEval,
} from '../api/profiling'

const CATEGORIES = ['', '后端', '前端', '算法', '产品', '数据', '测试', '运维']
const CHECK_STATES = ['掌握', '模糊', '不会'] as const

/** Compact match summary shown in the workbench (reuses MatchEval shape). */
function MiniMatch({ ev }: { ev: MatchEval }) {
  const { t } = useTranslation()
  return (
    <div className="mt-3 rounded-xl bg-surface px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="text-[22px] font-semibold tabular-nums text-accent">
          {Math.round(ev.score)}
        </span>
        <p className="text-[12px] leading-relaxed text-muted">{ev.summary}</p>
      </div>
      {ev.gaps.length > 0 && (
        <p className="mt-2 text-[11.5px] text-amber-600">
          △ {t('profiling.gapsCount', { count: ev.gaps.length })}:{' '}
          {ev.gaps.slice(0, 3).map((g) => g.requirement.slice(0, 14)).join('；')}
        </p>
      )}
    </div>
  )
}

/** Expanded job panel = prep workbench: match + self-check + CTAs. */
function Workbench({ job }: { job: JobPosition }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [checks, setChecks] = useState<Record<string, string>>({})
  const [evalResult, setEvalResult] = useState<MatchEval | null>(null)

  const { data: checkData } = useQuery({
    queryKey: ['self-check', job.id],
    queryFn: () => getSelfCheck(job.id),
  })
  useEffect(() => {
    if (checkData) setChecks(checkData.checks)
  }, [checkData])

  const analyze = useMutation({
    mutationFn: () => analyzeMatch({ job_id: job.id }),
    onSuccess: (data) => {
      setEvalResult(data)
      void queryClient.invalidateQueries({ queryKey: ['jobs'] })
    },
  })

  const onToggle = (point: string, state: string) => {
    const next = { ...checks }
    if (next[point] === state) delete next[point]
    else next[point] = state
    setChecks(next)
    void saveSelfCheck(job.id, next)
  }

  return (
    <div className="border-t border-line px-5 py-4">
      <p className="text-[13px] leading-relaxed text-muted">{job.description}</p>

      {/* ① my match */}
      <div className="mt-4">
        <div className="flex items-center gap-3">
          <p className="text-[11.5px] font-medium text-muted">{t('jobs.myScore')}</p>
          <button
            onClick={() => analyze.mutate()}
            disabled={analyze.isPending}
            className="rounded-full border border-line px-3 py-1 text-[11.5px] text-ink hover:border-accent hover:text-accent disabled:opacity-50"
          >
            {analyze.isPending
              ? t('jobs.evaluating')
              : job.my_score != null || evalResult
                ? t('jobs.reEvaluate')
                : t('jobs.evaluate')}
          </button>
        </div>
        {evalResult ? (
          <MiniMatch ev={evalResult} />
        ) : job.my_score != null ? (
          <div className="mt-2 flex items-center gap-2">
            <span className="text-[20px] font-semibold tabular-nums text-accent">
              {Math.round(job.my_score)}
            </span>
            <span className="text-[11.5px] text-faint">{t('profiling.aiTitle')}</span>
          </div>
        ) : null}
      </div>

      {/* ② self-check */}
      <div className="mt-5">
        <p className="text-[11.5px] font-medium text-muted">{t('jobs.selfCheckTitle')}</p>
        <p className="mt-0.5 text-[11px] text-faint">{t('jobs.selfCheckHint')}</p>
        <div className="mt-2.5 space-y-1.5">
          {job.knowledge_points.map((point) => (
            <div key={point} className="flex flex-wrap items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-[12px] text-ink">{point}</span>
              <div className="flex gap-1">
                {CHECK_STATES.map((state) => {
                  const active = checks[point] === state
                  return (
                    <button
                      key={state}
                      onClick={() => onToggle(point, state)}
                      className={`rounded-full px-2.5 py-0.5 text-[10.5px] transition-colors ${
                        active
                          ? state === '掌握'
                            ? 'bg-emerald-50 text-emerald-700'
                            : state === '模糊'
                              ? 'bg-amber-50 text-amber-700'
                              : 'bg-red-50 text-red-600'
                          : 'border border-line text-faint hover:text-ink'
                      }`}
                    >
                      {t(`jobs.${state === '掌握' ? 'mastery' : state === '模糊' ? 'fuzzy' : 'unknown'}`)}
                    </button>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ③ CTAs */}
      <div className="mt-5 flex flex-wrap items-center gap-3">
        <button
          onClick={async () => {
            await toggleJobTarget(job.id, !job.is_target)
            void queryClient.invalidateQueries({ queryKey: ['jobs'] })
          }}
          className={`rounded-full px-4 py-2 text-[12px] transition-colors ${
            job.is_target
              ? 'bg-accent/10 text-accent'
              : 'border border-line text-ink hover:border-accent hover:text-accent'
          }`}
        >
          {job.is_target ? `★ ${t('jobs.targetRemove')}` : `☆ ${t('jobs.targetAdd')}`}
        </button>
        <Link
          to="/applications"
          className="rounded-full bg-accent px-5 py-2 text-[12px] font-medium text-white hover:bg-accent-hover"
        >
          {t('jobs.mockBtn')} →
        </Link>
      </div>
    </div>
  )
}

/** Jobs page = prep workbench (user UX redesign): match · self-check · target · practice. */
export default function Jobs() {
  const { t } = useTranslation()
  const [category, setCategory] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)

  const { data: jobs } = useQuery({
    queryKey: ['jobs', category],
    queryFn: () => listJobs(category || undefined),
  })
  const { data: profiles } = useQuery({ queryKey: ['job-profiles'], queryFn: listJobProfiles })

  return (
    <div className="mx-auto max-w-2xl pt-8">
      <h1 className="text-[26px] font-semibold tracking-tight text-ink">{t('page.jobsTitle')}</h1>
      <p className="mt-1.5 text-[13.5px] text-muted">{t('jobs.workbenchHint')}</p>

      <div className="mt-5 flex flex-wrap gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c || 'all'}
            onClick={() => setCategory(c)}
            className={`rounded-full px-3.5 py-1.5 text-[12.5px] transition-colors ${
              category === c ? 'bg-ink text-white' : 'border border-line text-muted hover:text-ink'
            }`}
          >
            {c ? t(`jobs.categories.${c}`) : t('jobs.all')}
          </button>
        ))}
      </div>

      <div className="mt-6 space-y-3">
        {(jobs ?? []).map((job: JobPosition) => (
          <div key={job.id} className="overflow-hidden rounded-2xl border border-line">
            <button
              className="flex w-full cursor-pointer items-center gap-3 px-5 py-4 text-left transition-colors hover:bg-surface/60"
              onClick={() => setExpanded(expanded === job.id ? null : job.id)}
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
                  <p className="text-[14.5px] font-medium text-ink">{job.title}</p>
                  {job.is_target && <span className="text-[12px] text-accent">★</span>}
                  <span className="text-[11.5px] text-faint">
                    {t(`jobs.categories.${job.category}`)} · {job.level}
                  </span>
                </div>
                <p className="mt-0.5 truncate text-[11.5px] text-faint">{job.description}</p>
              </div>
              {job.my_score != null && (
                <span className="shrink-0 rounded-full bg-accent/10 px-2.5 py-1 text-[11.5px] tabular-nums text-accent">
                  {t('jobs.myScore')} {Math.round(job.my_score)}
                </span>
              )}
              <span className="shrink-0 text-[12px] text-faint">{expanded === job.id ? '−' : '+'}</span>
            </button>
            {expanded === job.id && <Workbench job={job} />}
          </div>
        ))}
      </div>

      {/* my custom JDs — unified here with the catalog */}
      {(profiles ?? []).length > 0 && (
        <section className="mt-10">
          <h2 className="text-[15px] font-medium text-ink">{t('jobs.myJd')}</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {(profiles ?? []).map((p) => (
              <Link
                key={p.id}
                to="/profiling"
                className="rounded-full border border-line px-3.5 py-1.5 text-[12px] text-muted hover:border-faint hover:text-ink"
              >
                {p.title}
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
