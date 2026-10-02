import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { computePortrait, getPortrait, type ProfilingResult } from '../api/profiling'

function DirectionBars({ scores }: { scores: Record<string, number> }) {
  const { t } = useTranslation()
  return (
    <div className="space-y-2.5">
      {Object.entries(scores).map(([cat, score]) => (
        <div key={cat} className="flex items-center gap-3">
          <span className="w-12 shrink-0 text-[12.5px] text-muted">
            {t(`jobs.categories.${cat}`)}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface">
            <div
              className="h-full rounded-full bg-accent transition-all"
              style={{ width: `${Math.max(score, 3)}%` }}
            />
          </div>
          <span className="w-9 shrink-0 text-right text-[12px] tabular-nums text-faint">{score}</span>
        </div>
      ))}
    </div>
  )
}

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100)
  return (
    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border-2 border-accent text-[13px] font-semibold tabular-nums text-accent">
      {pct}
    </div>
  )
}

/** Portrait + job recommendations (PLAN.md §5.2 / §7). */
export default function Profiling() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [error, setError] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['profiling'],
    queryFn: () => getPortrait().catch(() => null),
  })

  const compute = useMutation({
    mutationFn: () => computePortrait(),
    onSuccess: (result: ProfilingResult) => {
      queryClient.setQueryData(['profiling'], result)
      setError('')
    },
    onError: () => setError(t('profiling.needResume')),
  })

  const result: ProfilingResult | null = (data as ProfilingResult | null) ?? null

  return (
    <div className="mx-auto max-w-3xl pt-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-semibold tracking-tight text-ink">
            {t('profiling.title')}
          </h1>
          <p className="mt-1.5 text-[13.5px] text-muted">{t('profiling.desc')}</p>
        </div>
        <button
          onClick={() => compute.mutate()}
          disabled={compute.isPending}
          className="shrink-0 rounded-full bg-accent px-5 py-2.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {compute.isPending ? t('common.loading') : t('profiling.recompute')}
        </button>
      </div>

      {error && <p className="mt-4 text-[12.5px] text-red-600">{error}</p>}

      {!result && !isLoading && !error && (
        <div className="mt-10 rounded-2xl border border-dashed border-line py-16 text-center">
          <p className="text-[13px] text-faint">{t('profiling.empty')}</p>
        </div>
      )}

      {result && (
        <>
          {/* portrait */}
          <section className="mt-8 rounded-2xl border border-line px-6 py-5">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
              <h2 className="text-[15px] font-medium text-ink">{t('profiling.portraitTitle')}</h2>
              <span className="rounded-full bg-surface px-2.5 py-0.5 text-[11.5px] text-muted">
                {t('profiling.experience')}: {result.portrait.experience_level}
              </span>
            </div>

            <p className="mt-5 text-[12px] text-muted">{t('profiling.directionTitle')}</p>
            <div className="mt-2.5">
              <DirectionBars scores={result.portrait.direction_scores} />
            </div>

            <p className="mt-6 text-[12px] text-muted">{t('profiling.strengths')}</p>
            <div className="mt-2.5 flex flex-wrap gap-2">
              {result.portrait.strengths.map((s) => (
                <span key={s} className="rounded-full border border-line px-3 py-1 text-[12px] text-ink">
                  {s}
                </span>
              ))}
            </div>

            {result.portrait.project_tags.length > 0 && (
              <>
                <p className="mt-6 text-[12px] text-muted">{t('profiling.tags')}</p>
                <div className="mt-2.5 flex flex-wrap gap-2">
                  {result.portrait.project_tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-accent/8 px-3 py-1 text-[12px] text-accent"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </>
            )}
          </section>

          {/* recommendations */}
          <section className="mt-8">
            <h2 className="text-[15px] font-medium text-ink">{t('profiling.recsTitle')}</h2>
            <div className="mt-4 space-y-4">
              {result.recommendations.map((rec) => (
                <div key={rec.id} className="rounded-2xl border border-line px-6 py-5">
                  <div className="flex items-start gap-4">
                    <ScoreBadge score={rec.score} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-baseline gap-x-3">
                        <h3 className="text-[15px] font-medium text-ink">{rec.job.title}</h3>
                        <span className="text-[12px] text-faint">
                          {t(`jobs.categories.${rec.job.category}`)} · {rec.job.level}
                        </span>
                      </div>
                      <ul className="mt-2 space-y-1">
                        {rec.reasons.map((r, i) => (
                          <li key={i} className="text-[12.5px] text-muted">
                            <span className="mr-1.5 text-accent">✓</span>
                            {r}
                          </li>
                        ))}
                      </ul>
                      {rec.matched_skills.length > 0 && (
                        <div className="mt-2.5 flex flex-wrap gap-1.5">
                          {rec.matched_skills.slice(0, 8).map((m) => (
                            <span
                              key={m.skill}
                              className="rounded-md bg-surface px-2 py-0.5 text-[11px] text-muted"
                            >
                              {m.skill}
                            </span>
                          ))}
                        </div>
                      )}
                      {rec.gap_skills.some((g) => g.required) && (
                        <p className="mt-2 text-[11.5px] text-amber-600">
                          {t('profiling.gaps')}:{' '}
                          {rec.gap_skills
                            .filter((g) => g.required)
                            .map((g) => g.skill)
                            .join('、')}
                        </p>
                      )}
                    </div>
                    <Link
                      to="/applications"
                      className="shrink-0 rounded-full border border-line px-4 py-2 text-[12px] text-ink transition-colors hover:border-faint"
                    >
                      {t('profiling.startMock')}
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  )
}
