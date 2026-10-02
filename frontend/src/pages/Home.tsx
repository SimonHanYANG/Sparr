import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

/** Hero: big type, whitespace, one primary CTA — DeepSeek/Apple minimal (PLAN.md §7). */
export default function Home() {
  const { t } = useTranslation()

  const features = [
    { title: t('home.feature1Title'), desc: t('home.feature1Desc') },
    { title: t('home.feature2Title'), desc: t('home.feature2Desc') },
    { title: t('home.feature3Title'), desc: t('home.feature3Desc') },
  ]

  return (
    <div className="pb-6">
      <section className="mx-auto max-w-2xl pt-16 text-center sm:pt-24">
        <p className="mb-4 text-[12px] font-medium uppercase tracking-[0.2em] text-accent">
          {t('home.tagline')}
        </p>
        <h1 className="text-[34px] font-semibold leading-tight tracking-tight text-ink sm:text-[46px]">
          {t('home.title')}
        </h1>
        <p className="mx-auto mt-5 max-w-xl text-[15px] leading-relaxed text-muted sm:text-base">
          {t('home.subtitle')}
        </p>
        <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            to="/resumes"
            className="w-full rounded-full bg-accent px-7 py-3 text-[14.5px] font-medium text-white transition-colors hover:bg-accent-hover sm:w-auto"
          >
            {t('home.ctaPrimary')}
          </Link>
          <Link
            to="/applications"
            className="w-full rounded-full border border-line px-7 py-3 text-[14.5px] font-medium text-ink transition-colors hover:border-faint sm:w-auto"
          >
            {t('home.ctaSecondary')}
          </Link>
        </div>
      </section>

      <section className="mx-auto mt-24 grid max-w-4xl gap-10 sm:grid-cols-3">
        {features.map((f, i) => (
          <div key={i} className="text-center sm:text-left">
            <div className="mx-auto mb-3 h-px w-8 bg-accent sm:mx-0" />
            <h3 className="text-[15px] font-medium text-ink">{f.title}</h3>
            <p className="mt-2 text-[13.5px] leading-relaxed text-muted">{f.desc}</p>
          </div>
        ))}
      </section>
    </div>
  )
}
