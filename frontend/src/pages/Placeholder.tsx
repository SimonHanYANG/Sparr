import { useTranslation } from 'react-i18next'

/** Generic page shell for Phase 0 skeletons: title, description, empty state. */
export default function Placeholder({
  titleKey,
  descKey,
}: {
  titleKey: string
  descKey: string
}) {
  const { t } = useTranslation()
  return (
    <div className="mx-auto max-w-2xl pt-8">
      <h1 className="text-[26px] font-semibold tracking-tight text-ink">{t(titleKey)}</h1>
      <p className="mt-2 text-[14px] text-muted">{t(descKey)}</p>
      <div className="mt-12 rounded-2xl border border-dashed border-line py-16 text-center">
        <p className="text-[13px] text-faint">{t('page.empty')}</p>
      </div>
    </div>
  )
}
