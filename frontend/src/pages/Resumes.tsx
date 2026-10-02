import { useQuery } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { deleteResume, listResumes, reparseResume, uploadResume } from '../api/resumes'
import type { ParseStatus, Resume } from '../types/resume'

const statusColor: Record<ParseStatus, string> = {
  uploaded: 'bg-surface text-muted',
  parsing: 'bg-accent/10 text-accent',
  parsed: 'bg-emerald-50 text-emerald-700',
  failed: 'bg-red-50 text-red-600',
}

function StatusBadge({ status }: { status: ParseStatus }) {
  const { t } = useTranslation()
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-[11.5px] ${statusColor[status]}`}>
      {t(`resume.status.${status}`)}
    </span>
  )
}

/** Resume list: framed upload zone + parse hint + cards with delete (user feedback). */
export default function Resumes() {
  const { t } = useTranslation()
  const fileInput = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')

  const { data: resumes, refetch } = useQuery({
    queryKey: ['resumes'],
    queryFn: listResumes,
    refetchInterval: (query) =>
      (query.state.data ?? []).some((r) => r.parse_status === 'uploaded' || r.parse_status === 'parsing')
        ? 4000
        : false,
  })

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setError('')
    setUploading(true)
    try {
      await uploadResume(file)
      await refetch()
    } catch {
      setError(t('resume.uploadFailed'))
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const onDelete = async (r: Resume) => {
    if (!window.confirm(t('resume.deleteConfirm'))) return
    await deleteResume(r.id)
    await refetch()
  }

  const onReparse = async (r: Resume) => {
    await reparseResume(r.id)
    await refetch()
  }

  const needsParse = (resumes ?? []).filter(
    (r) => r.parse_status === 'uploaded' || r.parse_status === 'failed',
  )
  const parsingNow = (resumes ?? []).some((r) => r.parse_status === 'parsing')

  return (
    <div className="mx-auto max-w-2xl pt-8">
      <h1 className="text-[26px] font-semibold tracking-tight text-ink">{t('page.resumesTitle')}</h1>
      <p className="mt-1.5 text-[13.5px] text-muted">{t('page.resumesDesc')}</p>

      {/* upload frame with the button inside */}
      <div className="mt-6 rounded-2xl border border-dashed border-line py-10 text-center">
        <p className="text-[14px] font-medium text-ink">{t('resume.uploadTitle')}</p>
        <p className="mt-1 text-[12px] text-faint">{t('resume.uploadHint')}</p>
        <button
          onClick={() => fileInput.current?.click()}
          disabled={uploading}
          className="mt-4 rounded-full bg-accent px-6 py-2.5 text-[13.5px] font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {uploading ? t('resume.uploading') : t('resume.upload')}
        </button>
        <input ref={fileInput} type="file" accept=".pdf" className="hidden" onChange={onFile} />
      </div>

      {error && <p className="mt-3 text-[12.5px] text-red-600">{error}</p>}

      {/* one-line parse hint when resumes are waiting for parse */}
      {(needsParse.length > 0 || parsingNow) && (
        <div className="mt-3 flex items-center gap-2 text-[12.5px] text-muted">
          <span className="h-1.5 w-1.5 rounded-full bg-accent" />
          {parsingNow ? (
            <span>{t('resume.parsingSoon')}</span>
          ) : (
            <>
              <span>
                {t('resume.parsePrompt', { title: needsParse[0].title })}
              </span>
              <button
                className="text-accent hover:underline"
                onClick={() => onReparse(needsParse[0])}
              >
                {t('resume.parseNow')}
              </button>
            </>
          )}
        </div>
      )}

      <div className="mt-6 space-y-3">
        {(resumes ?? []).map((r: Resume) => (
          <div
            key={r.id}
            className="flex items-center gap-4 rounded-2xl border border-line px-5 py-4 transition-colors hover:border-faint"
          >
            <Link to={`/resumes/${r.id}`} className="min-w-0 flex-1">
              <p className="truncate text-[15px] font-medium text-ink">{r.title}</p>
              <p className="mt-0.5 truncate text-[12px] text-faint">
                {r.source_filename} · {new Date(r.updated_at).toLocaleDateString()}
              </p>
            </Link>
            <StatusBadge status={r.parse_status} />
            <button
              className="shrink-0 text-[12px] text-muted transition-colors hover:text-red-600"
              onClick={() => onDelete(r)}
            >
              {t('resume.delete')}
            </button>
          </div>
        ))}

        {resumes && resumes.length === 0 && (
          <div className="rounded-2xl border border-dashed border-line py-12 text-center">
            <p className="text-[13px] text-faint">{t('resume.empty')}</p>
          </div>
        )}
      </div>
    </div>
  )
}
