import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import {
  analyzeCatalogStream,
  analyzeMatch,
  computePortrait,
  createJobProfile,
  listJobProfiles,
  type MatchEval,
} from '../api/profiling'

function ScoreBadge({ score }: { score: number }) {
  const color = score >= 75 ? 'border-accent text-accent' : score >= 60 ? 'border-amber-500 text-amber-600' : 'border-faint text-muted'
  return (
    <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-full border-2 text-[13px] font-semibold tabular-nums ${color}`}>
      {Math.round(score)}
    </div>
  )
}

/** One LLM match evaluation card — collapsed by default, expandable. */
function MatchCard({ ev }: { ev: MatchEval }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const label = ev.job_profile ? ev.job_profile.title : (ev.job?.title ?? '')
  const levels = ev.job?.levels ?? (ev.job ? [ev.job.level] : [])
  const keyGaps = ev.gaps.filter((g) => g.status === '未体现').slice(0, 2)

  return (
    <div className="animate-fade overflow-hidden rounded-2xl border border-line transition-shadow hover:shadow-sm">
      {/* collapsed header — always visible key info */}
      <button
        onClick={() => setOpen(!open)}
        className="group flex w-full cursor-pointer items-start gap-4 px-6 py-5 text-left transition-colors hover:bg-surface/60"
      >
        <ScoreBadge score={ev.score} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <h3 className="text-[14.5px] font-medium text-ink">{label}</h3>
            {levels.length > 0 && (
              <span className="rounded-full bg-surface px-2 py-0.5 text-[10.5px] text-muted">
                {levels.join(' / ')}
              </span>
            )}
          </div>
          {ev.summary && <p className="mt-1 text-[12.5px] text-muted">{ev.summary}</p>}
          {ev.gaps.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10.5px] text-amber-700">
                {t('profiling.gapsCount', { count: ev.gaps.length })}
              </span>
              {keyGaps.map((g, i) => (
                <span key={i} className="text-[11px] text-faint">
                  {g.requirement.slice(0, 12)}
                  {g.requirement.length > 12 ? '…' : ''}
                </span>
              ))}
            </div>
          )}
        </div>
        {/* clickable-looking pill: hover turns accent */}
        <span className="flex shrink-0 items-center gap-1 rounded-full border border-line px-3 py-1 text-[11.5px] text-muted transition-colors group-hover:border-accent group-hover:text-accent">
          {open ? t('profiling.collapse') : t('profiling.detailPill')}
          <span className={`text-[10px] transition-transform ${open ? 'rotate-180' : ''}`}>⌄</span>
        </span>
      </button>

      {/* expanded details */}
      {open && (
        <div className="animate-fade border-t border-line px-6 py-4">
          {ev.matched.length > 0 && (
            <>
              <p className="text-[11.5px] font-medium text-emerald-700">
                ✓ {t('profiling.matchedTitle')}
              </p>
              <ul className="mt-1.5 space-y-1">
                {ev.matched.slice(0, 5).map((m, i) => (
                  <li key={i} className="text-[12px] leading-relaxed text-muted">
                    <span className="text-ink">{m.requirement}</span>
                    <span className="mx-1 text-faint">←</span>
                    {m.evidence}
                  </li>
                ))}
              </ul>
            </>
          )}

          {ev.gaps.length > 0 && (
            <>
              <p className="mt-3 text-[11.5px] font-medium text-amber-600">
                △ {t('profiling.gapsTitle')}
              </p>
              <ul className="mt-1.5 space-y-1.5">
                {ev.gaps.slice(0, 5).map((g, i) => (
                  <li key={i} className="text-[12px] leading-relaxed">
                    <span className="text-ink">{g.requirement}</span>
                    <span className="ml-1.5 rounded bg-amber-50 px-1.5 py-0.5 text-[10.5px] text-amber-700">
                      {g.status}
                    </span>
                    {g.advice && <span className="text-muted"> — {g.advice}</span>}
                  </li>
                ))}
              </ul>
            </>
          )}

          {ev.advice.length > 0 && (
            <p className="mt-3 text-[12px] leading-relaxed text-muted">💡 {ev.advice.join('；')}</p>
          )}

          <div className="mt-4 flex items-center justify-between">
            <button className="text-[12px] text-muted hover:text-ink" onClick={() => setOpen(false)}>
              {t('profiling.collapse')}
            </button>
            <Link
              to="/applications"
              className="rounded-full border border-line px-4 py-2 text-[12px] text-ink transition-colors hover:border-faint"
            >
              {t('profiling.startMock')}
            </Link>
          </div>
        </div>
      )}
    </div>
  )
}

/** Animated placeholder shown while waiting for streamed results. */
function SkeletonCard() {
  return (
    <div className="animate-pulse rounded-2xl border border-line px-6 py-5">
      <div className="flex items-start gap-4">
        <div className="h-12 w-12 shrink-0 rounded-full bg-surface" />
        <div className="flex-1 space-y-2.5">
          <div className="h-3.5 w-1/3 rounded bg-surface" />
          <div className="h-3 w-5/6 rounded bg-surface" />
          <div className="h-3 w-2/3 rounded bg-surface" />
          <div className="h-3 w-3/4 rounded bg-surface" />
        </div>
      </div>
    </div>
  )
}

/** Portrait quick-signal + AI match evaluations + custom JD analysis (PLAN.md §5.2). */
export default function Profiling() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [evals, setEvals] = useState<MatchEval[]>([])
  const [jdTitle, setJdTitle] = useState('')
  const [jdText, setJdText] = useState('')
  const [error, setError] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [progress, setProgress] = useState({ done: 0, total: 0 })
  const [selectedCount, setSelectedCount] = useState(0)

  const { data: portraitResult } = useQuery({
    queryKey: ['profiling'],
    queryFn: () => computePortrait().catch(() => null),
  })
  const { data: profiles } = useQuery({
    queryKey: ['job-profiles'],
    queryFn: listJobProfiles,
  })

  const runCatalog = async () => {
    setError('')
    setStreaming(true)
    setEvals([])
    setProgress({ done: 0, total: 0 })
    try {
      await analyzeCatalogStream(
        (ev, prog) => {
          setEvals((prev) => [...prev, ev])
          setProgress(prog)
        },
        (prog) => setProgress(prog),
        (meta) => {
          setSelectedCount(meta.total)
          setProgress((p) => ({ ...p, total: meta.total }))
        },
      )
    } catch {
      setError(t('profiling.analyzeFailed'))
    } finally {
      setStreaming(false)
    }
  }

  const single = useMutation({
    mutationFn: analyzeMatch,
    onSuccess: (data) => {
      setEvals((prev) => [data, ...prev.filter((e) => e.job_profile?.id !== data.job_profile?.id)])
      setError('')
    },
    onError: () => setError(t('profiling.analyzeFailed')),
  })

  const onAnalyzeJd = async () => {
    if (!jdTitle.trim() || !jdText.trim()) return
    setError('')
    try {
      const profile = await createJobProfile(jdTitle.trim(), jdText.trim())
      void queryClient.invalidateQueries({ queryKey: ['job-profiles'] })
      single.mutate({ job_profile_id: profile.id })
      setJdText('')
    } catch {
      setError(t('profiling.analyzeFailed'))
    }
  }

  const inputCls =
    'w-full rounded-xl border border-line bg-white px-3.5 py-2 text-[13px] text-ink outline-none focus:border-accent'

  return (
    <div className="mx-auto max-w-3xl pt-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[26px] font-semibold tracking-tight text-ink">{t('profiling.title')}</h1>
          <p className="mt-1.5 text-[13.5px] text-muted">{t('profiling.aiDesc')}</p>
        </div>
        <button
          onClick={runCatalog}
          disabled={streaming || single.isPending}
          className="shrink-0 rounded-full bg-accent px-5 py-2.5 text-[13px] font-medium text-white hover:bg-accent-hover disabled:opacity-50"
        >
          {streaming
            ? t('profiling.analyzingProgress', { done: progress.done, total: progress.total || 12 })
            : t('profiling.analyzeCatalog')}
        </button>
      </div>

      {error && <p className="mt-4 text-[12.5px] text-red-600">{error}</p>}

      {/* custom JD analysis */}
      <section className="mt-8 rounded-2xl border border-line px-6 py-5">
        <h2 className="text-[15px] font-medium text-ink">{t('profiling.pasteJdTitle')}</h2>
        <p className="mt-1 text-[12px] text-faint">{t('profiling.pasteJdHint')}</p>
        <div className="mt-3 space-y-3">
          <input
            className={inputCls}
            placeholder={t('profiling.jdTitlePh')}
            value={jdTitle}
            onChange={(e) => setJdTitle(e.target.value)}
          />
          <textarea
            className={`${inputCls} h-32 resize-none leading-relaxed`}
            placeholder={t('profiling.jdTextPh')}
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
          />
          <button
            onClick={onAnalyzeJd}
            disabled={!jdTitle.trim() || !jdText.trim() || single.isPending}
            className="rounded-full bg-accent px-5 py-2 text-[12.5px] font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {single.isPending ? t('common.loading') : t('profiling.analyzeJd')}
          </button>
        </div>
        {(profiles ?? []).length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {(profiles ?? []).map((p) => (
              <button
                key={p.id}
                onClick={() => single.mutate({ job_profile_id: p.id })}
                className="rounded-full border border-line px-3 py-1 text-[11.5px] text-muted hover:border-faint hover:text-ink"
              >
                ↻ {p.title}
              </button>
            ))}
          </div>
        )}
      </section>

      {/* AI evaluations */}
      {(evals.length > 0 || streaming) && (
        <section className="mt-8">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
            <h2 className="text-[15px] font-medium text-ink">{t('profiling.aiTitle')}</h2>
            <p className="text-[11.5px] text-faint">
              {t('profiling.modelNote', { model: evals[0]?.model_name || 'mimo-v2.6-flash' })}
            </p>
          </div>

          {/* live progress while streaming */}
          {streaming && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-[11.5px] text-muted">
                <span>
                  {t('profiling.streamProgress', {
                    done: progress.done,
                    total: progress.total || 12,
                  })}
                </span>
                <span className="text-faint">
                  {selectedCount > 0
                    ? t('profiling.selectedHint', { count: selectedCount })
                    : t('profiling.streamHint')}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-surface">
                <div
                  className="h-full rounded-full bg-accent transition-all duration-500"
                  style={{
                    width: `${Math.round((progress.done / progress.total) * 100)}%`,
                  }}
                />
              </div>
            </div>
          )}

          <div className="mt-4 space-y-4">
            {evals.map((ev, i) => (
              <MatchCard key={ev.id ?? `local-${i}`} ev={ev} />
            ))}

            {/* skeletons while waiting for the first cards */}
            {streaming &&
              Array.from({ length: Math.min(2, progress.total - progress.done) }).map(
                (_, i) => <SkeletonCard key={`sk-${i}`} />,
              )}
          </div>

          {/* tail: still working on the rest */}
          {streaming && progress.done > 0 && (
            <div className="mt-4 flex items-center gap-2.5 rounded-2xl border border-dashed border-line px-5 py-3.5">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              <span className="text-[12.5px] text-muted">
                {t('profiling.tailLoading', {
                  count: Math.max(progress.total - progress.done, 0),
                })}
              </span>
            </div>
          )}
        </section>
      )}

      {evals.length === 0 && !streaming && (
        <div className="mt-8 rounded-2xl border border-dashed border-line py-14 text-center">
          <p className="text-[13px] text-faint">{t('profiling.empty')}</p>
        </div>
      )}

      {/* rule-based quick signal */}
      {portraitResult && (
        <section className="mt-10 rounded-2xl border border-line px-6 py-5">
          <h2 className="text-[15px] font-medium text-ink">{t('profiling.quickSignal')}</h2>
          <p className="mt-1 text-[11.5px] text-faint">{t('profiling.quickSignalHint')}</p>
          <div className="mt-4 space-y-2.5">
            {Object.entries(portraitResult.portrait.direction_scores).map(([cat, score]) => (
              <div key={cat} className="flex items-center gap-3">
                <span className="w-12 shrink-0 text-[12.5px] text-muted">
                  {t(`jobs.categories.${cat}`)}
                </span>
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-surface">
                  <div className="h-full rounded-full bg-accent/60" style={{ width: `${Math.max(score, 3)}%` }} />
                </div>
                <span className="w-9 shrink-0 text-right text-[12px] tabular-nums text-faint">{score}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            {portraitResult.portrait.strengths.map((s) => (
              <span key={s} className="rounded-full border border-line px-3 py-1 text-[11.5px] text-ink">
                {s}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
