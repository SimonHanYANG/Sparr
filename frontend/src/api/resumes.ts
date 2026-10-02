import { apiFetch, apiUpload } from './client'
import type { Resume, ResumeDetail, ResumeVersion, StructuredResume } from '../types/resume'

export function uploadResume(file: File, title?: string): Promise<Resume> {
  const form = new FormData()
  form.append('file', file)
  if (title) form.append('title', title)
  return apiUpload<Resume>('/api/resumes/upload', form)
}

export const listResumes = () => apiFetch<Resume[]>('/api/resumes')

export const getResume = (id: number) => apiFetch<ResumeDetail>(`/api/resumes/${id}`)

export const deleteResume = (id: number) =>
  apiFetch<void>(`/api/resumes/${id}`, { method: 'DELETE' })

export const reparseResume = (id: number) =>
  apiFetch<Resume>(`/api/resumes/${id}/reparse`, { method: 'POST' })

export const listVersions = (id: number) =>
  apiFetch<ResumeVersion[]>(`/api/resumes/${id}/versions`)

export const getVersion = (id: number, vid: number) =>
  apiFetch<ResumeVersion>(`/api/resumes/${id}/versions/${vid}`)

export const saveVersion = (id: number, structured_json: StructuredResume, change_note: string) =>
  apiFetch<ResumeVersion>(`/api/resumes/${id}/versions`, {
    method: 'POST',
    body: JSON.stringify({ structured_json, change_note }),
  })

export const rollbackVersion = (id: number, vid: number) =>
  apiFetch<ResumeVersion>(`/api/resumes/${id}/versions/${vid}/rollback`, { method: 'POST' })
