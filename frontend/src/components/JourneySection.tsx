import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { apiFetch } from '../api/client'

export interface FlowStep {
  key: string
  label: string
  url: string
  action: string
  desc: string
  status: 'done' | 'active' | 'todo'
}

export interface FlowState {
  steps: FlowStep[]
  next: FlowStep | null
  current: FlowStep | null
  meta: { resume_title?: string; resume_status?: string }
}

export const useFlow = () =>
  useQuery({ queryKey: ['flow'], queryFn: () => apiFetch<FlowState>('/api/flow/state') })

function StepDot({ step, index }: { step: FlowStep; index: number }) {
  const { t } = useTranslation()
  const done = step.status === 'done'
  const active = step.status === 'active'
  return (
    <Link to={step.url} className="group flex min-w-0 flex-1 items-center gap-2">
      <span
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11.5px] transition-colors ${
          done
            ? 'bg-accent text-white'
            : active
              ? 'border-2 border-accent bg-white text-accent'
              : 'border border-line bg-white text-faint'
        }`}
      >
        {done ? '✓' : index + 1}
      </span>
      <span
        className={`truncate text-[12.5px] ${
          done || active ? 'font-medium text-ink' : 'text-faint'
        } group-hover:text-accent`}
      >
        {t(`flow.steps.${step.key}`)}
      </span>
    </Link>
  )
}

/** Main-line journey: 4-step progress + dynamic next-action card (PLAN UX redesign). */
export default function JourneySection() {
  const { t } = useTranslation()
  const { data: flow } = useFlow()
  if (!flow) return null

  const next = flow.next

  return (
    <section className="mt-12">
      {/* progress bar */}
      <div className="flex items-center gap-1 sm:gap-2">
        {flow.steps.map((step, i) => (
          <div key={step.key} className="flex min-w-0 flex-1 items-center gap-1 sm:gap-2">
            <StepDot step={step} index={i} />
            {i < flow.steps.length - 1 && (
              <span
                className={`h-px min-w-3 flex-1 ${step.status === 'done' ? 'bg-accent' : 'bg-line'}`}
              />
            )}
          </div>
        ))}
      </div>

      {/* next action card */}
      {next && (
        <div className="mt-6 flex flex-wrap items-center gap-4 rounded-2xl border border-line px-7 py-6">
          <div className="min-w-0 flex-1">
            <p className="text-[11.5px] uppercase tracking-wider text-accent">
              {t('flow.nextLabel')}
            </p>
            <h3 className="mt-1 text-[17px] font-medium text-ink">
              {t(`flow.actions.${next.key}`)}
            </h3>
            <p className="mt-1 text-[13px] text-muted">
              {t(`flow.descs.${next.key}`)}
              {next.key === 'resume' && flow.meta.resume_title
                ? `（${flow.meta.resume_title}）`
                : ''}
            </p>
          </div>
          <Link
            to={next.url}
            className="shrink-0 rounded-full bg-accent px-6 py-2.5 text-[13.5px] font-medium text-white transition-colors hover:bg-accent-hover"
          >
            {t('flow.go')} →
          </Link>
        </div>
      )}

      {!next && (
        <div className="mt-6 rounded-2xl border border-line px-7 py-6 text-center">
          <p className="text-[14px] text-ink">{t('flow.allDone')}</p>
          <Link to="/resumes" className="mt-2 inline-block text-[12.5px] text-accent hover:underline">
            {t('flow.again')}
          </Link>
        </div>
      )}
    </section>
  )
}

/** Bottom-of-page connector: what to do after the current page. */
export function NextStepBar({ currentKey }: { currentKey: string }) {
  const { t } = useTranslation()
  const { data: flow } = useFlow()
  if (!flow) return null
  const steps = flow.steps
  const idx = steps.findIndex((s) => s.key === currentKey)
  const after = steps.slice(idx + 1).find((s) => s.status !== 'done')
  const target = after ?? flow.next
  if (!target || target.key === currentKey) return null

  return (
    <div className="mt-12 flex items-center justify-between gap-4 rounded-2xl bg-surface px-6 py-4">
      <div className="min-w-0">
        <p className="text-[11px] uppercase tracking-wider text-faint">{t('flow.nextLabel')}</p>
        <p className="mt-0.5 truncate text-[13.5px] font-medium text-ink">
          {t(`flow.actions.${target.key}`)}
        </p>
      </div>
      <Link
        to={target.url}
        className="shrink-0 rounded-full border border-line bg-white px-5 py-2 text-[12.5px] text-ink transition-colors hover:border-accent hover:text-accent"
      >
        {t('flow.go')} →
      </Link>
    </div>
  )
}
