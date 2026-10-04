import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

import {
  createApplication,
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
  const [search, setSearch] = useState('')
  const [duration, setDuration] = useState(30)
  const [strict, setStrict] = useState(false)

  const { data: sessions } = useQuery({
    queryKey: ['applications'],
    queryFn: listApplications,
  })
  const { data: jobs } = useQuery({ queryKey: ['jobs'], queryFn: () => listJobs() })
  const { data: profiles } = useQuery({ queryKey: ['job-profiles'], queryFn: listJobProfiles })

  // 高匹配岗位从高到低；其余走搜索，不再塞满下拉框
  const recommended = useMemo(
    () =>
      (jobs ?? [])
        .filter((j) => j.my_score != null)
        .sort((a, b) => (b.my_score ?? 0) - (a.my_score ?? 0))
        .slice(0, 6),
    [jobs],
  )
  const searchResults = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return []
    return (jobs ?? [])
      .filter((j) => `${j.title}${j.category}${j.level}`.toLowerCase().includes(q))
      .slice(0, 24)
  }, [jobs, search])

  const pickJob = (id: number) => {
    setJobId(id)
    setProfileId('')
  }

  // 创建很快（不等 LLM）——立即进面试间，面试计划在房间里流式生成
  const create = useMutation({
    mutationFn: () =>
      createApplication({
        job_id: jobId === '' ? undefined : jobId,
        job_profile_id: profileId === '' ? undefined : profileId,
        duration_min: duration,
        strict_mode: strict,
      }),
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

        {/* ① 高匹配岗位卡片（按匹配度从高到低） */}
        <p className="mt-4 text-[11.5px] font-medium text-muted">{t('interview.recommended')}</p>
        {recommended.length > 0 ? (
          <>
            <p className="mt-0.5 text-[11px] text-faint">{t('interview.recommendedHint')}</p>
            <div className="mt-2.5 grid grid-cols-2 gap-2.5 sm:grid-cols-3">
              {recommended.map((j: JobPosition) => (
                <button
                  key={j.id}
                  onClick={() => pickJob(j.id)}
                  className={`rounded-2xl border px-4 py-3 text-left transition-colors ${
                    jobId === j.id
                      ? 'border-accent bg-accent/5'
                      : 'border-line hover:border-faint'
                  }`}
                >
                  <p className="truncate text-[13px] font-medium text-ink">{j.title}</p>
                  <p className="mt-0.5 text-[10.5px] text-faint">
                    {t(`jobs.categories.${j.category}`)} · {j.level}
                  </p>
                  <p className="mt-1 text-[17px] font-semibold tabular-nums text-accent">
                    {Math.round(j.my_score ?? 0)}
                    <span className="ml-1 text-[10px] font-normal text-muted">
                      {t('jobs.myScore')}
                    </span>
                  </p>
                </button>
              ))}
            </div>
          </>
        ) : (
          <p className="mt-1.5 rounded-xl bg-surface px-4 py-3 text-[11.5px] leading-relaxed text-muted">
            {t('interview.noScore')}{' '}
            <Link to="/profiling" className="text-accent hover:underline">
              {t('interview.goProfiling')} →
            </Link>
          </p>
        )}

        {/* ② 其余岗位走搜索 */}
        <p className="mt-5 text-[11.5px] font-medium text-muted">{t('interview.otherJobs')}</p>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('interview.searchPh')}
          className="mt-2 w-full rounded-full border border-line bg-white px-4 py-2 text-[13px] text-ink placeholder:text-faint focus:border-accent focus:outline-none"
        />
        {search.trim() ? (
          searchResults.length > 0 ? (
            <div className="mt-2.5 flex flex-wrap gap-2">
              {searchResults.map((j: JobPosition) => (
                <button
                  key={j.id}
                  onClick={() => pickJob(j.id)}
                  className={`rounded-full border px-3.5 py-1.5 text-[12px] transition-colors ${
                    jobId === j.id
                      ? 'border-accent bg-accent/5 text-accent'
                      : 'border-line text-muted hover:border-faint hover:text-ink'
                  }`}
                >
                  {j.title}（{j.level}）
                  {j.my_score != null && (
                    <span className="ml-1 tabular-nums text-accent">{Math.round(j.my_score)}</span>
                  )}
                </button>
              ))}
            </div>
          ) : (
            <p className="mt-2 text-[11.5px] text-faint">{t('interview.searchEmpty')}</p>
          )
        ) : (
          <p className="mt-1.5 text-[11px] text-faint">{t('interview.searchHint')}</p>
        )}

        {/* ③ 自定义 JD */}
        {(profiles ?? []).length > 0 && (
          <>
            <p className="mt-5 text-[11.5px] font-medium text-muted">{t('interview.customJd')}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {(profiles ?? []).map((p) => (
                <button
                  key={p.id}
                  onClick={() => {
                    setProfileId(p.id)
                    setJobId('')
                  }}
                  className={`rounded-full border px-3.5 py-1.5 text-[12px] transition-colors ${
                    profileId === p.id
                      ? 'border-accent bg-accent/5 text-accent'
                      : 'border-line text-muted hover:border-faint hover:text-ink'
                  }`}
                >
                  {p.title}
                </button>
              ))}
            </div>
          </>
        )}

        {/* ④ 时长 / 严格模式 / 创建 */}
        <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-3">
          <label className="flex items-center gap-2">
            <span className="text-[11.5px] text-muted">{t('interview.duration')}</span>
            <select
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="rounded-xl border border-line bg-white px-3 py-1.5 text-[13px] text-ink"
            >
              {DURATIONS.map((d) => (
                <option key={d} value={d}>
                  {d} {t('interview.minutes')}
                </option>
              ))}
            </select>
          </label>
          <label className="flex cursor-pointer items-center gap-2">
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
                  {s.status === 'finished' ? t('interview.view') : t('interview.continue')} →
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
