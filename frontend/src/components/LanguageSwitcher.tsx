import { currentLang, setLang } from '../i18n'

/** 中 / EN pill toggle — persists to localStorage (PLAN.md §7 i18n). */
export default function LanguageSwitcher() {
  const lang = currentLang()
  return (
    <div className="flex items-center rounded-full border border-line p-0.5 text-[12px]">
      <button
        onClick={() => setLang('zh-CN')}
        className={`rounded-full px-2.5 py-1 transition-colors ${
          lang === 'zh-CN' ? 'bg-ink text-white' : 'text-muted hover:text-ink'
        }`}
      >
        中
      </button>
      <button
        onClick={() => setLang('en')}
        className={`rounded-full px-2.5 py-1 transition-colors ${
          lang === 'en' ? 'bg-ink text-white' : 'text-muted hover:text-ink'
        }`}
      >
        EN
      </button>
    </div>
  )
}
