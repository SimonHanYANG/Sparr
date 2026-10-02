import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { listJobs, type JobPosition } from '../api/profiling'

const CATEGORIES = ['', '后端', '前端', '算法', '产品', '数据', '测试', '运维']

/** Job catalog browse (PLAN.md §7). */
export default function Jobs() {
  const { t } = useTranslation()
  const [category, setCategory] = useState('')
  const [expanded, setExpanded] = useState<number | null>(null)

  const { data: jobs } = useQuery({
    queryKey: ['jobs', category],
    queryFn: () => listJobs(category || undefined),
  })

  return (
    <div className="mx-auto max-w-2xl pt-8">
      <h1 className="text-[26px] font-semibold tracking-tight text-ink">{t('page.jobsTitle')}</h1>
      <p className="mt-1.5 text-[13.5px] text-muted">{t('page.jobsDesc')}</p>

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
          <div key={job.id} className="rounded-2xl border border-line">
            <button
              className="flex w-full items-center gap-3 px-5 py-4 text-left"
              onClick={() => setExpanded(expanded === job.id ? null : job.id)}
            >
              <div className="min-w-0 flex-1">
                <p className="text-[14.5px] font-medium text-ink">{job.title}</p>
                <p className="mt-0.5 text-[12px] text-faint">
                  {t(`jobs.categories.${job.category}`)} · {job.level}
                </p>
              </div>
              <span className="text-[12px] text-faint">{expanded === job.id ? '−' : '+'}</span>
            </button>
            {expanded === job.id && (
              <div className="border-t border-line px-5 py-4">
                <p className="text-[13px] leading-relaxed text-muted">{job.description}</p>

                <p className="mt-4 text-[11.5px] font-medium text-muted">
                  {t('jobs.skills')}
                </p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {job.skill_requirements.map((s) => (
                    <span
                      key={s.skill}
                      className={`rounded-md px-2 py-0.5 text-[11px] ${
                        s.required ? 'bg-accent/8 text-accent' : 'bg-surface text-muted'
                      }`}
                    >
                      {s.skill} {s.required ? '·必会' : `·${s.weight}`}
                    </span>
                  ))}
                </div>

                <p className="mt-4 text-[11.5px] font-medium text-muted">
                  {t('jobs.knowledgePoints')}
                </p>
                <p className="mt-1 text-[12px] leading-relaxed text-ink">
                  {job.knowledge_points.join('、')}
                </p>

                <p className="mt-3 text-[11.5px] font-medium text-muted">
                  {t('jobs.codingTopics')}
                </p>
                <p className="mt-1 text-[12px] leading-relaxed text-ink">
                  {job.coding_topics.join('、')}
                </p>

                <p className="mt-3 text-[11.5px] font-medium text-muted">
                  {t('jobs.interviewFocus')}
                </p>
                <p className="mt-1 text-[12px] leading-relaxed text-ink">
                  {job.interview_focus.join('、')}
                </p>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
