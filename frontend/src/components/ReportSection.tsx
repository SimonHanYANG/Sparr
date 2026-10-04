import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  decideSuggestion,
  generateReport,
  getReport,
  type FinalReport,
  type ResumeSuggestion,
} from '../api/applications'

const RADAR_DIMS = ['基础知识', '编码能力', '项目深度', '沟通表达', '岗位匹配']

/** 综合总结报告（§5.4）：三段汇总 + 简历修改建议采纳闭环。 */
export default function ReportSection({ sessionId }: { sessionId: number }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [elapsed, setElapsed] = useState(0)

  const { data } = useQuery({
    queryKey: ['report', sessionId],
    queryFn: () => getReport(sessionId),
  })
  const gen = useMutation({
    mutationFn: () => generateReport(sessionId),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['report', sessionId] }),
  })
  useEffect(() => {
    if (!gen.isPending) return
    const timer = window.setInterval(() => setElapsed((e) => e + 1), 1000)
    return () => window.clearInterval(timer)
  }, [gen.isPending])

  if (gen.isPending)
    return (
      <div className="mt-2">
        <div className="orbit-wrap">
          <div className="rounded-2xl border border-line px-6 py-7">
            <p className="text-[13.5px] font-medium text-ink">{t('report.generating')}</p>
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

  const report = data?.report ?? null
  if (!report)
    return (
      <div className="mt-2 rounded-2xl border border-line px-6 py-8 text-center">
        <p className="text-[13.5px] text-ink">{t('report.emptyTitle')}</p>
        <p className="mt-1 text-[12px] text-muted">{t('report.hint')}</p>
        {gen.isError && <p className="mt-2 text-[12px] text-red-600">{t('report.genError')}</p>}
        <button
          onClick={() => gen.mutate()}
          className="mt-4 rounded-full bg-accent px-6 py-2.5 text-[13px] font-medium text-white hover:bg-accent-hover"
        >
          {t('report.genBtn')}
        </button>
      </div>
    )

  return (
    <div className="mt-2">
      <ReportCard report={report} sessionId={sessionId} />
    </div>
  )
}

function ReportCard({ report, sessionId }: { report: FinalReport; sessionId: number }) {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const decide = useMutation({
    mutationFn: ({ sugId, accept }: { sugId: number; accept: boolean }) =>
      decideSuggestion(sessionId, sugId, accept),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['report', sessionId] }),
  })

  return (
    <div className="rounded-2xl border border-line px-6 py-5">
      {/* 综合结论 */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="text-[15px] font-medium text-ink">{t('report.title')}</p>
        <span
          className={`rounded-full px-2.5 py-0.5 text-[11px] ${
            report.hire_recommendation === '强推' || report.hire_recommendation === '推荐'
              ? 'bg-emerald-50 text-emerald-700'
              : report.hire_recommendation === '不推荐'
                ? 'bg-red-50 text-red-600'
                : 'bg-amber-50 text-amber-700'
          }`}
        >
          {t(`interview.hire.${report.hire_recommendation}`)}
        </span>
        <span className="ml-auto text-[26px] font-semibold tabular-nums text-accent">
          {Math.round(report.overall_score)}
          <span className="ml-1 text-[11px] font-normal text-muted">{t('report.outOf')}</span>
        </span>
      </div>

      {/* 五维雷达（条形） */}
      <p className="mt-4 text-[11.5px] font-medium text-muted">{t('report.radar')}</p>
      <div className="mt-2 space-y-1.5">
        {RADAR_DIMS.filter((d) => report.dimension_radar[d] != null).map((d) => (
          <div key={d} className="flex items-center gap-3">
            <span className="w-16 shrink-0 text-[11.5px] text-muted">{t(`report.dims.${d}`)}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface">
              <div
                className="h-full rounded-full bg-accent/70"
                style={{ width: `${report.dimension_radar[d]}%` }}
              />
            </div>
            <span className="w-8 shrink-0 text-right text-[11.5px] tabular-nums text-ink">
              {report.dimension_radar[d]}
            </span>
          </div>
        ))}
      </div>

      {/* 分段小结 */}
      {report.per_stage_summary.length > 0 && (
        <>
          <p className="mt-4 text-[11.5px] font-medium text-muted">{t('report.stageSummaries')}</p>
          <div className="mt-2 space-y-2">
            {report.per_stage_summary.map((s, i) => (
              <div key={i} className="rounded-xl bg-surface px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <p className="text-[12px] font-medium text-ink">{s.stage}</p>
                  <span className="text-[11px] tabular-nums text-accent">{s.score}</span>
                </div>
                <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{s.summary}</p>
              </div>
            ))}
          </div>
        </>
      )}

      {/* 强项 / 硬伤 */}
      {report.highlights.length > 0 && (
        <>
          <p className="mt-4 text-[11.5px] font-medium text-emerald-700">
            {t('report.highlights')}
          </p>
          <ul className="mt-1.5 space-y-1">
            {report.highlights.map((h, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-ink">
                · {h}
              </li>
            ))}
          </ul>
        </>
      )}
      {report.weaknesses.length > 0 && (
        <>
          <p className="mt-3 text-[11.5px] font-medium text-amber-700">{t('report.weaknesses')}</p>
          <ul className="mt-1.5 space-y-1">
            {report.weaknesses.map((w, i) => (
              <li key={i} className="text-[12px] leading-relaxed text-ink">
                · {w}
              </li>
            ))}
          </ul>
        </>
      )}

      {/* 改进计划 */}
      {report.improvement_plan.length > 0 && (
        <>
          <p className="mt-4 text-[11.5px] font-medium text-muted">{t('report.improvement')}</p>
          <div className="mt-2 space-y-2">
            {report.improvement_plan.map((item, i) => (
              <div key={i} className="rounded-xl bg-surface px-4 py-2.5">
                <p className="text-[12px] font-medium text-ink">{item.area}</p>
                <p className="mt-1 text-[11.5px] leading-relaxed text-muted">{item.action}</p>
              </div>
            ))}
          </div>
        </>
      )}

      {/* 简历修改建议（diff + 采纳闭环） */}
      {report.suggestions.length > 0 && (
        <>
          <p className="mt-4 text-[11.5px] font-medium text-muted">{t('report.suggestions')}</p>
          <p className="mt-0.5 text-[11px] text-faint">{t('report.suggestionsHint')}</p>
          <div className="mt-2 space-y-2.5">
            {report.suggestions.map((s) => (
              <SuggestionCard
                key={s.id}
                sug={s}
                busy={decide.isPending}
                onDecide={(accept) => decide.mutate({ sugId: s.id, accept })}
              />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function SuggestionCard({
  sug,
  busy,
  onDecide,
}: {
  sug: ResumeSuggestion
  busy: boolean
  onDecide: (accept: boolean) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="rounded-xl border border-line px-4 py-3">
      {sug.field_path && (
        <p className="text-[10.5px] text-faint">{sug.field_path}</p>
      )}
      <div className="mt-1.5 grid gap-1.5 sm:grid-cols-2">
        <div className="rounded-lg bg-red-50/60 px-3 py-2">
          <p className="text-[10.5px] font-medium text-red-500">{t('report.original')}</p>
          <p className="mt-0.5 text-[11.5px] leading-relaxed text-ink line-through decoration-red-300">
            {sug.original_text}
          </p>
        </div>
        <div className="rounded-lg bg-emerald-50/60 px-3 py-2">
          <p className="text-[10.5px] font-medium text-emerald-600">{t('report.suggested')}</p>
          <p className="mt-0.5 text-[11.5px] leading-relaxed text-ink">{sug.suggested_text}</p>
        </div>
      </div>
      <p className="mt-1.5 text-[11px] leading-relaxed text-muted">💡 {sug.reason}</p>
      {sug.status === 'pending' ? (
        <div className="mt-2 flex gap-2">
          <button
            onClick={() => onDecide(true)}
            disabled={busy}
            className="rounded-full bg-accent px-4 py-1.5 text-[11.5px] font-medium text-white hover:bg-accent-hover disabled:opacity-50"
          >
            {t('report.accept')}
          </button>
          <button
            onClick={() => onDecide(false)}
            disabled={busy}
            className="rounded-full border border-line px-4 py-1.5 text-[11.5px] text-muted hover:border-faint hover:text-ink disabled:opacity-50"
          >
            {t('report.reject')}
          </button>
        </div>
      ) : (
        <p className="mt-2 text-[11px] text-faint">
          {sug.status === 'accepted' ? `✓ ${t('report.accepted')}` : `✗ ${t('report.rejected')}`}
          {sug.apply_note ? ` · ${sug.apply_note}` : ''}
        </p>
      )}
    </div>
  )
}
