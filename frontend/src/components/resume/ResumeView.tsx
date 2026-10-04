import { useTranslation } from 'react-i18next'

import type { StructuredResume } from '../../types/resume'

/** 列表字段防御性归一化：脏数据/手改/旧版本里字段可能是标量，统一成数组再渲染。 */
function arr<T>(v: T[] | T | undefined | null): T[] {
  if (Array.isArray(v)) return v
  if (v == null || v === '') return []
  return [v as T]
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="text-[13px] font-medium uppercase tracking-wider text-muted">{title}</h2>
      <div className="mt-3">{children}</div>
    </section>
  )
}

/** Card-style online resume (PLAN.md §7). */
export default function ResumeView({ data }: { data: StructuredResume }) {
  const { t } = useTranslation()
  const basics = data.basics ?? { name: '', intent_role: '', contact: '', years_exp: '' }
  const education = arr(data.education)
  const skills = arr(data.skills)
  const projects = arr(data.projects)
  const work = arr(data.work_experiences)
  const awards = arr(data.awards)

  return (
    <div>
      {/* basics header */}
      <div>
        <h1 className="text-[28px] font-semibold tracking-tight text-ink">
          {basics.name || t('resume.sections.basics')}
        </h1>
        <p className="mt-1 text-[14px] text-accent">{basics.intent_role}</p>
        <p className="mt-1 text-[12.5px] text-muted">
          {[basics.contact, basics.years_exp].filter(Boolean).join(' · ')}
        </p>
      </div>

      {skills.length > 0 && (
        <Section title={t('resume.sections.skills')}>
          <div className="space-y-2">
            {skills.map((s, i) => (
              <div key={i} className="flex flex-wrap items-baseline gap-x-2.5 text-[13px]">
                <span className="font-medium text-ink">{s.name}</span>
                {s.level && (
                  <span className="rounded-full bg-surface px-2 py-0.5 text-[11px] text-muted">
                    {s.level}
                  </span>
                )}
                {s.desc && <span className="text-muted">{s.desc}</span>}
              </div>
            ))}
          </div>
        </Section>
      )}

      {projects.length > 0 && (
        <Section title={t('resume.sections.projects')}>
          <div className="space-y-5">
            {projects.map((p, i) => (
              <div key={i} className="rounded-2xl border border-line px-5 py-4">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <h3 className="text-[15px] font-medium text-ink">{p.name}</h3>
                  <p className="text-[12px] text-faint">
                    {[p.role, p.period].filter(Boolean).join(' · ')}
                  </p>
                </div>
                {arr(p.tech_stack).length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {arr(p.tech_stack).map((tech, j) => (
                      <span key={j} className="rounded-md bg-surface px-2 py-0.5 text-[11.5px] text-muted">
                        {tech}
                      </span>
                    ))}
                  </div>
                )}
                <ul className="mt-2.5 space-y-1">
                  {arr(p.bullets).map((b, j) => (
                    <li key={j} className="text-[13px] leading-relaxed text-ink">
                      <span className="mr-1.5 text-faint">·</span>
                      {b}
                    </li>
                  ))}
                </ul>
                {arr(p.metrics).length > 0 && (
                  <div className="mt-2.5 flex flex-wrap gap-2">
                    {arr(p.metrics).map((m, j) => (
                      <span key={j} className="rounded-full bg-accent/8 px-2.5 py-0.5 text-[11.5px] text-accent">
                        {m}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {work.length > 0 && (
        <Section title={t('resume.sections.work')}>
          <div className="space-y-4">
            {work.map((w, i) => (
              <div key={i}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                  <h3 className="text-[14.5px] font-medium text-ink">
                    {w.company}
                    {w.role && <span className="ml-2 text-muted">{w.role}</span>}
                  </h3>
                  <p className="text-[12px] text-faint">{w.period}</p>
                </div>
                <ul className="mt-1.5 space-y-1">
                  {arr(w.bullets).map((b, j) => (
                    <li key={j} className="text-[13px] leading-relaxed text-ink">
                      <span className="mr-1.5 text-faint">·</span>
                      {b}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Section>
      )}

      {education.length > 0 && (
        <Section title={t('resume.sections.education')}>
          <div className="space-y-3">
            {education.map((e, i) => (
              <div key={i} className="flex flex-wrap items-baseline justify-between gap-x-3">
                <div>
                  <h3 className="text-[14px] font-medium text-ink">{e.school}</h3>
                  <p className="text-[12.5px] text-muted">
                    {[e.major, e.degree].filter(Boolean).join(' · ')}
                  </p>
                  {e.desc && <p className="mt-0.5 text-[12px] text-faint">{e.desc}</p>}
                </div>
                <p className="text-[12px] text-faint">{e.period}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {awards.length > 0 && (
        <Section title={t('resume.sections.awards')}>
          <ul className="space-y-1">
            {awards.map((a, i) => (
              <li key={i} className="text-[13px] text-ink">
                <span className="mr-1.5 text-faint">·</span>
                {String(a)}
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  )
}
