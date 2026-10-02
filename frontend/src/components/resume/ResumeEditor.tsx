import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import type { StructuredResume } from '../../types/resume'

const input =
  'w-full rounded-xl border border-line bg-white px-3.5 py-2 text-[13.5px] text-ink outline-none focus:border-accent'
const label = 'block text-[11.5px] text-muted mb-1'

function linesToArray(text: string): string[] {
  return text.split('\n').map((s) => s.trim()).filter(Boolean)
}

/** Structured resume editor — arrays edited as item cards / line-textareas (PLAN.md §5.1). */
export default function ResumeEditor({
  initial,
  onSave,
}: {
  initial: StructuredResume
  onSave: (data: StructuredResume, changeNote: string) => Promise<void>
}) {
  const { t } = useTranslation()
  const [data, setData] = useState<StructuredResume>(structuredClone(initial))
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)

  const patch = (mut: (d: StructuredResume) => void) => {
    setData((prev) => {
      const next = structuredClone(prev)
      mut(next)
      return next
    })
  }

  const F = t

  return (
    <div className="space-y-8">
      {/* basics */}
      <section>
        <h2 className="text-[13px] font-medium uppercase tracking-wider text-muted">
          {t('resume.sections.basics')}
        </h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {(
            [
              ['name', data.basics.name],
              ['intentRole', data.basics.intent_role],
              ['contact', data.basics.contact],
              ['yearsExp', data.basics.years_exp],
            ] as const
          ).map(([key, value]) => (
            <div key={key}>
              <span className={label}>{F(`resume.fields.${key}`)}</span>
              <input
                className={input}
                value={value}
                onChange={(e) =>
                  patch((d) => {
                    const map: Record<string, 'name' | 'intent_role' | 'contact' | 'years_exp'> = {
                      name: 'name',
                      intentRole: 'intent_role',
                      contact: 'contact',
                      yearsExp: 'years_exp',
                    }
                    d.basics[map[key]] = e.target.value
                  })
                }
              />
            </div>
          ))}
        </div>
      </section>

      {/* skills */}
      <section>
        <h2 className="text-[13px] font-medium uppercase tracking-wider text-muted">
          {t('resume.sections.skills')}
        </h2>
        <div className="mt-3 space-y-2">
          {data.skills.map((s, i) => (
            <div key={i} className="flex items-center gap-2">
              <input
                className={input}
                value={s.name}
                placeholder={t('resume.fields.skill')}
                onChange={(e) => patch((d) => void (d.skills[i].name = e.target.value))}
              />
              <input
                className={`${input} w-32 shrink-0`}
                value={s.level}
                placeholder={t('resume.fields.level')}
                onChange={(e) => patch((d) => void (d.skills[i].level = e.target.value))}
              />
              <button
                className="shrink-0 text-[12px] text-muted hover:text-red-600"
                onClick={() => patch((d) => void d.skills.splice(i, 1))}
              >
                {t('resume.remove')}
              </button>
            </div>
          ))}
          <button
            className="text-[12.5px] text-accent hover:underline"
            onClick={() => patch((d) => void d.skills.push({ name: '', level: '' }))}
          >
            + {t('resume.add')}
          </button>
        </div>
      </section>

      {/* projects */}
      <section>
        <h2 className="text-[13px] font-medium uppercase tracking-wider text-muted">
          {t('resume.sections.projects')}
        </h2>
        <div className="mt-3 space-y-4">
          {data.projects.map((p, i) => (
            <div key={i} className="rounded-2xl border border-line p-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <input
                  className={input}
                  value={p.name}
                  placeholder={t('resume.fields.project')}
                  onChange={(e) => patch((d) => void (d.projects[i].name = e.target.value))}
                />
                <input
                  className={input}
                  value={p.role}
                  placeholder={t('resume.fields.role')}
                  onChange={(e) => patch((d) => void (d.projects[i].role = e.target.value))}
                />
                <input
                  className={input}
                  value={p.period}
                  placeholder={t('resume.fields.period')}
                  onChange={(e) => patch((d) => void (d.projects[i].period = e.target.value))}
                />
              </div>
              <div className="mt-3">
                <span className={label}>{t('resume.fields.techStack')}</span>
                <input
                  className={input}
                  value={p.tech_stack.join(', ')}
                  onChange={(e) =>
                    patch((d) =>
                      void (d.projects[i].tech_stack = e.target.value
                        .split(/[，,]/)
                        .map((s) => s.trim())
                        .filter(Boolean)),
                    )
                  }
                />
              </div>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <span className={label}>{t('resume.fields.bullets')}</span>
                  <textarea
                    className={`${input} h-28 resize-none leading-relaxed`}
                    value={p.bullets.join('\n')}
                    onChange={(e) =>
                      patch((d) => void (d.projects[i].bullets = linesToArray(e.target.value)))
                    }
                  />
                </div>
                <div>
                  <span className={label}>{t('resume.fields.metrics')}</span>
                  <textarea
                    className={`${input} h-28 resize-none leading-relaxed`}
                    value={p.metrics.join('\n')}
                    onChange={(e) =>
                      patch((d) => void (d.projects[i].metrics = linesToArray(e.target.value)))
                    }
                  />
                </div>
              </div>
              <button
                className="mt-3 text-[12px] text-muted hover:text-red-600"
                onClick={() => patch((d) => void d.projects.splice(i, 1))}
              >
                {t('resume.remove')}
              </button>
            </div>
          ))}
          <button
            className="text-[12.5px] text-accent hover:underline"
            onClick={() =>
              patch((d) =>
                void d.projects.push({
                  name: '', role: '', period: '', tech_stack: [], bullets: [], metrics: [],
                }),
              )
            }
          >
            + {t('resume.add')}
          </button>
        </div>
      </section>

      {/* work */}
      <section>
        <h2 className="text-[13px] font-medium uppercase tracking-wider text-muted">
          {t('resume.sections.work')}
        </h2>
        <div className="mt-3 space-y-4">
          {data.work_experiences.map((w, i) => (
            <div key={i} className="rounded-2xl border border-line p-4">
              <div className="grid gap-3 sm:grid-cols-3">
                <input
                  className={input}
                  value={w.company}
                  placeholder={t('resume.fields.company')}
                  onChange={(e) => patch((d) => void (d.work_experiences[i].company = e.target.value))}
                />
                <input
                  className={input}
                  value={w.role}
                  placeholder={t('resume.fields.role')}
                  onChange={(e) => patch((d) => void (d.work_experiences[i].role = e.target.value))}
                />
                <input
                  className={input}
                  value={w.period}
                  placeholder={t('resume.fields.period')}
                  onChange={(e) => patch((d) => void (d.work_experiences[i].period = e.target.value))}
                />
              </div>
              <div className="mt-3">
                <span className={label}>{t('resume.fields.bullets')}</span>
                <textarea
                  className={`${input} h-24 resize-none leading-relaxed`}
                  value={w.bullets.join('\n')}
                  onChange={(e) =>
                    patch((d) => void (d.work_experiences[i].bullets = linesToArray(e.target.value)))
                  }
                />
              </div>
              <button
                className="mt-3 text-[12px] text-muted hover:text-red-600"
                onClick={() => patch((d) => void d.work_experiences.splice(i, 1))}
              >
                {t('resume.remove')}
              </button>
            </div>
          ))}
          <button
            className="text-[12.5px] text-accent hover:underline"
            onClick={() =>
              patch((d) =>
                void d.work_experiences.push({ company: '', role: '', period: '', bullets: [] }),
              )
            }
          >
            + {t('resume.add')}
          </button>
        </div>
      </section>

      {/* education */}
      <section>
        <h2 className="text-[13px] font-medium uppercase tracking-wider text-muted">
          {t('resume.sections.education')}
        </h2>
        <div className="mt-3 space-y-4">
          {data.education.map((e, i) => (
            <div key={i} className="rounded-2xl border border-line p-4">
              <div className="grid gap-3 sm:grid-cols-2">
                {(
                  ['school', 'degree', 'major', 'period'] as const
                ).map((key) => (
                  <input
                    key={key}
                    className={input}
                    value={e[key]}
                    placeholder={t(`resume.fields.${key}`)}
                    onChange={(ev) => patch((d) => void (d.education[i][key] = ev.target.value))}
                  />
                ))}
              </div>
              <button
                className="mt-3 text-[12px] text-muted hover:text-red-600"
                onClick={() => patch((d) => void d.education.splice(i, 1))}
              >
                {t('resume.remove')}
              </button>
            </div>
          ))}
          <button
            className="text-[12.5px] text-accent hover:underline"
            onClick={() =>
              patch((d) =>
                void d.education.push({ school: '', degree: '', major: '', period: '', desc: '' }),
              )
            }
          >
            + {t('resume.add')}
          </button>
        </div>
      </section>

      {/* awards */}
      <section>
        <h2 className="text-[13px] font-medium uppercase tracking-wider text-muted">
          {t('resume.sections.awards')}
        </h2>
        <div className="mt-3">
          <textarea
            className={`${input} h-24 resize-none leading-relaxed`}
            value={data.awards.join('\n')}
            placeholder={t('resume.fields.award')}
            onChange={(e) => patch((d) => void (d.awards = linesToArray(e.target.value)))}
          />
        </div>
      </section>

      {/* save bar */}
      <div className="flex flex-col gap-3 border-t border-line pt-5 sm:flex-row sm:items-center">
        <input
          className={`${input} sm:max-w-xs`}
          placeholder={t('resume.saveNote')}
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <button
          disabled={busy}
          onClick={async () => {
            setBusy(true)
            try {
              await onSave(data, note)
              setNote('')
            } finally {
              setBusy(false)
            }
          }}
          className="rounded-full bg-accent px-6 py-2.5 text-[13.5px] font-medium text-white transition-colors hover:bg-accent-hover disabled:opacity-50 sm:ml-auto"
        >
          {busy ? t('common.loading') : t('resume.save')}
        </button>
      </div>
    </div>
  )
}
