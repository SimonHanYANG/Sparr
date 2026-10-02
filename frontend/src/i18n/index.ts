import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import { en, zh } from './locales'

const LANG_KEY = 'sparr_lang'

export function currentLang(): string {
  return localStorage.getItem(LANG_KEY) ?? 'zh-CN'
}

export function setLang(lang: 'zh-CN' | 'en') {
  localStorage.setItem(LANG_KEY, lang)
  void i18n.changeLanguage(lang)
  document.documentElement.lang = lang
}

i18n.use(initReactI18next).init({
  resources: {
    'zh-CN': { translation: zh },
    en: { translation: en },
  },
  lng: currentLang(),
  fallbackLng: 'zh-CN',
  interpolation: { escapeValue: false },
})

document.documentElement.lang = currentLang()

export default i18n
