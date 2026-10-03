import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

import {
  createApplication,
  generatePlan,
  listApplications,
  type ApplicationListItem,
} from '../api/applications'
import { listJobProfiles, listJobs, type JobPosition } from '../api/profiling'

const DURATIONS = [15, 30, 45]

/** Mock-interview sessions: 断点续面 list + new-session form (PLAN.md §5.3③-B). */
export default function Applications() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [jobId, setJobId] = useState<number | ''>('')
  const [profileId, setProfileId] = useState<number | ''>('')
  const [duration, setDuration] = useState(30)
  const [strict, setStrict] = useState(false)

  const { data: sessions } = useQuery({
    queryKey: ['applications'],
    queryFn: listApplications,
  })
  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: () => listJobs() })
  const { data: profiles } = useQuery({ queryKey: ['job-profiles'], queryFn: listJobProfiles })

  const create = useMutation({
    mutationFn: async () => {
      const session = await createApplication({
        job_id: jobId === '' ? undefined : jobId,
        job_profile_id: profileId === '' ? undefined : profileId,
        duration_min: duration,
        strict_mode: strict,
      })
      await generatePlan(session.id) // 面试计划一次生成、永久复用
      return session
    },
    onSuccess: (session) => {
      void queryClient.invalidateQueries({ queryKey: ['applications'] })
      navigate(`/applications/${session.id}`)
    },
  })

  const canCreate = jobId !== '' || profileId !== ''

  return (
    <div className="mx-auto max-w-2xl pt-8">
      <h1 className="text-[26px] font-semibold tracking-tight text-ink">
        {t('page.applicationsTitle')}
      </h1>
      <p className="mt-1.5 text-[13.5px] text-muted">{t('page.applicationsDesc')}</p>

      {/* new session */}
      <section className="mt-6 rounded-2xl border border-line px-6 py-5">
        <p className="text-[13px] font-medium text-ink">{t('interview.newSession')}</p>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="text-[11.5px] text-muted">{t('interview.pickJob')}</span>
            <select
              value={jobId}
              onChange={(e) => {
                setJobId(e.target.value === '' ? '' : Number(e.target.value))
                setProfileId('')
              }}
              className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2 text-[13px] text-ink"
            >
              <option value="">{t('interview.choose')}</option>
              {(jobs ?? []).map((j: JobPosition) => (
                <option key={j.id} value={j.id}>
                  {j.title}（{j.level}）
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-[11.5px] text-muted">{t('interview.pickCustom')}</span>
            <select
              value={profileId}
              onChange={(e) => {
                setProfileId(e.target.value === '' ? '' : Number(e.target.value))
                setJobId('')
              }}
              className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2 text-[13px] text-ink"
            >
              <option value="">{t('interview.choose')}</option>
              {(profiles ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.title}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-[11.5px] text-muted">{t('interview.duration')}</span>
            <select
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="mt-1 w-full rounded-xl border border-line bg-white px-3 py-2 text-[13px] text-ink"
            >
              {DURATIONS.map((d) => (
                <option key={d} value={d}>
                  {d} {t('interview.minutes')}
                </option>
              ))}
            </select>
          </label>
          <label className="flex cursor-pointer items-center gap-2 pt-5">
            <input
              type="checkbox"
              checked={strict}
              onChange={(e) => setStrict(e.target.checked)}
              className="h-4 w-4 accent-accent"
            />
            <span className="text-[12.5px] text-ink">{t('interview.strictMode')}</span>
          </label>
        </div>
        {create.isError && (
          <p className="mt-2 text-[12px] text-red-600">{t('interview.createError')}</p>
        )}
        <button
          onClick={() => create.mutate()}
          disabled={!canCreate || create.isPending}
          className="mt-4 rounded-full bg-accent px-6 py-2.5 text-[13px] font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {create.isPending ? t('interview.creating') : t('interview.create')}
        </button>
      </section>

      {/* session list — 断点续面入口 */}
      {(sessions ?? []).length > 0 && (
        <section className="mt-8">
          <p className="text-[13px] font-medium text-ink">{t('interview.mySessions')}</p>
          <div className="mt-3 space-y-2.5">
            {(sessions ?? []).map((s: ApplicationListItem) => (
              <Link
                key={s.id}
                to={`/applications/${s.id}`}
                className="flex items-center gap-3 rounded-2xl border border-line px-5 py-3.5 transition-colors hover:border-faint"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[14px] font-medium text-ink">{s.job_title}</p>
                  <p className="mt-0.5 text-[11.5px] text-faint">
                    {t(`interview.status.${s.status}`)}
                    {s.last_turn_seq > 0 &&
                      ` · ${t('interview.turnsCount', { count: Math.ceil(s.last_turn_seq / 2) })}`}
                    {' · '}
                    {s.updated_at.slice(0, 10)}
                  </p>
                </div>
                <span className="shrink-0 text-[12.5px] text-accent">
                  {s.status === 'finished'
                    ? t('interview.view')
                    : t('interview.continue')}{' '}
                  →
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
