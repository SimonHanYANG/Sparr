import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useParams } from 'react-router-dom'

import {
  getResume,
  getVersion,
  reparseResume,
  replaceResumePdf,
  rollbackVersion,
  saveVersion,
} from '../api/resumes'
import ResumeEditor from '../components/resume/ResumeEditor'
import ResumeView from '../components/resume/ResumeView'
import type { StructuredResume } from '../types/resume'

type Tab = 'view' | 'edit' | 'versions'

const tabCls = (active: boolean) =>
  `rounded-full px-4 py-1.5 text-[13px] transition-colors ${
    active ? 'bg-ink text-white' : 'text-muted hover:text-ink'
  }`

/** Resume detail: card view / editor + source / version history (PLAN.md §5.1). */
export default function ResumeDetail() {
  const { t } = useTranslation()
  const { id } = useParams()
  const resumeId = Number(id)
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('view')
  const [toast, setToast] = useState('')
  const replaceInput = useRef<HTMLInputElement>(null)

  const { data: resume, isError, isLoading } = useQuery({
    queryKey: ['resume', resumeId],
    queryFn: () => getResume(resumeId),
    refetchInterval: (q) =>
      q.state.data && ['uploaded', 'parsing'].includes(q.state.data.parse_status) ? 4000 : false,
  })

  const { data: version } = useQuery({
    queryKey: ['resume-version', resumeId, resume?.current_version?.id],
    queryFn: () => getVersion(resumeId, resume!.current_version!.id),
    enabled: Boolean(resume?.current_version),
  })

  const flash = (msg: string) => {
    setToast(msg)
    setTimeout(() => setToast(''), 2500)
  }

  if (isError) {
    return (
      <div className="mx-auto max-w-2xl pt-20 text-center">
        <p className="text-[15px] text-ink">{t('resume.notFound')}</p>
        <a href="/resumes" className="mt-3 inline-block text-[13px] text-accent hover:underline">
          ← {t('page.resumesTitle')}
        </a>
      </div>
    )
  }
  if (isLoading || !resume) return null

  const parsing = ['uploaded', 'parsing'].includes(resume.parse_status)
  const failed = resume.parse_status === 'failed'
  const ready = Boolean(version)

  return (
    <div className="mx-auto max-w-3xl pt-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight text-ink">{resume.title}</h1>
          <p className="mt-1 text-[12px] text-faint">
            {resume.source_filename || t('resume.manualBadge')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {failed && (
            <button
              onClick={async () => {
                await reparseResume(resumeId)
                void queryClient.invalidateQueries({ queryKey: ['resume', resumeId] })
              }}
              className="rounded-full border border-line px-4 py-2 text-[12.5px] text-ink hover:border-faint"
            >
              {t('resume.reparse')}
            </button>
          )}
          <button
            onClick={() => replaceInput.current?.click()}
            className="rounded-full border border-line px-4 py-2 text-[12.5px] text-ink hover:border-faint"
          >
            {t('resume.replacePdf')}
          </button>
          <input
            ref={replaceInput}
            type="file"
            accept=".pdf"
            className="hidden"
            onChange={async (e) => {
              const file = e.target.files?.[0]
              if (!file) return
              await replaceResumePdf(resumeId, file)
              await queryClient.invalidateQueries({ queryKey: ['resume', resumeId] })
              setTab('view')
              e.target.value = ''
            }}
          />
        </div>
      </div>

      {parsing && (
        <div className="mt-8 rounded-2xl border border-dashed border-line py-14 text-center">
          <p className="text-[14px] text-ink">{t('resume.parsing')}</p>
          <p className="mt-1.5 text-[12px] text-faint">{t('resume.parseHint')}</p>
        </div>
      )}

      {failed && (
        <div className="mt-6 rounded-2xl bg-red-50 px-5 py-4">
          <p className="text-[13px] font-medium text-red-600">{t('resume.status.failed')}</p>
          <p className="mt-1 text-[12.5px] text-red-600/80">{resume.parse_error}</p>
          {/API-Key|设置/.test(resume.parse_error) && (
            <a href="/settings" className="mt-1.5 inline-block text-[12.5px] font-medium text-red-600 underline">
              {t('resume.goSettings')}
            </a>
          )}
        </div>
      )}

      {(ready || failed) && !parsing && (
        <>
          <nav className="mt-6 flex flex-wrap gap-2">
            {(['view', 'edit', 'versions'] as Tab[]).map((key) => (
              <button key={key} className={tabCls(tab === key)} onClick={() => setTab(key)}>
                {t(`resume.${key === 'view' ? 'view' : key}`)}
              </button>
            ))}
          </nav>

          <div className="mt-6">
            {tab === 'view' && ready && <ResumeView data={version!.structured_json} />}

            {tab === 'edit' && ready && (
              <ResumeEditor
                key={version!.id}
                initial={version!.structured_json}
                onSave={async (data: StructuredResume, note: string) => {
                  await saveVersion(resumeId, data, note)
                  await queryClient.invalidateQueries({ queryKey: ['resume', resumeId] })
                  flash(t('resume.saved'))
                  setTab('view')
                }}
              />
            )}

            {tab === 'versions' && (
              <div className="space-y-2">
                {(resume.versions ?? []).map((v) => (
                  <div
                    key={v.id}
                    className="flex flex-wrap items-center gap-3 rounded-2xl border border-line px-5 py-3.5"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-[13.5px] font-medium text-ink">
                        {t('resume.version')} {v.version_no}
                        {v.id === resume.current_version?.id && (
                          <span className="ml-2 rounded-full bg-accent/10 px-2 py-0.5 text-[10.5px] text-accent">
                            {t('resume.current')}
                          </span>
                        )}
                      </p>
                      <p className="mt-0.5 text-[11.5px] text-faint">
                        {v.change_note || '—'} · {new Date(v.created_at).toLocaleString()}
                      </p>
                    </div>
                    {v.id !== resume.current_version?.id && (
                      <button
                        className="text-[12px] text-accent hover:underline"
                        onClick={async () => {
                          await rollbackVersion(resumeId, v.id)
                          await queryClient.invalidateQueries({ queryKey: ['resume', resumeId] })
                          flash(t('resume.rolledBack'))
                          setTab('view')
                        }}
                      >
                        {t('resume.rollback')}
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

          </div>
        </>
      )}

      {toast && (
        <div className="fixed bottom-8 left-1/2 -translate-x-1/2 rounded-full bg-ink px-5 py-2.5 text-[13px] text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  )
}
