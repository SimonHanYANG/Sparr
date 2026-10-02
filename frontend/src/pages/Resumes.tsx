import { useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useNavigate } from 'react-router-dom'

import { listResumes, uploadResume } from '../api/resumes'
import type { ParseStatus, Resume } from '../types/resume'
import { useQuery } from '@tanstack/react-query'

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

/** Resume list: upload + parse status (PLAN.md §7). */
export default function Resumes() {
  const { t } = useTranslation()
  const navigate = useNavigate()
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
      const resume = await uploadResume(file)
      await refetch()
      navigate(`/resumes/${resume.id}`)
    } catch {
      setError(t('auth.error'))
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  return (
    <div className="mx-auto max-w-2xl pt-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[26px] font-semibold tracking-tight text-ink">{t('page.resumesTitle')}</h1>
          <p className="mt-1.5 text-[13.5px] text-muted">{t('page.resumesDesc')}</p>
        </div>
        <button
          onClick={() => fileInput.current?.click()}
          disabled={uploading}
          className="shrink-0 rounded-full bg-accent px-5 py-2.5 text-[13.5px] font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
        >
          {uploading ? t('resume.uploading') : t('resume.upload')}
        </button>
        <input ref={fileInput} type="file" accept=".pdf" className="hidden" onChange={onFile} />
      </div>

      {error && <p className="mt-4 text-[13px] text-red-600">{error}</p>}

      <div className="mt-8 space-y-3">
        {(resumes ?? []).map((r: Resume) => (
          <Link
            key={r.id}
            to={`/resumes/${r.id}`}
            className="flex items-center gap-4 rounded-2xl border border-line px-5 py-4 transition-colors hover:border-faint"
          >
            <div className="min-w-0 flex-1">
              <p className="truncate text-[15px] font-medium text-ink">{r.title}</p>
              <p className="mt-0.5 truncate text-[12px] text-faint">
                {r.source_filename} · {new Date(r.updated_at).toLocaleDateString()}
              </p>
            </div>
            <StatusBadge status={r.parse_status} />
          </Link>
        ))}

        {resumes && resumes.length === 0 && (
          <div className="rounded-2xl border border-dashed border-line py-16 text-center">
            <p className="text-[13px] text-faint">{t('resume.empty')}</p>
          </div>
        )}
      </div>
    </div>
  )
}
