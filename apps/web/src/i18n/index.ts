import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import type { Language } from '@/lib/api'
import ar from './locales/ar.json'
import en from './locales/en.json'
import fr from './locales/fr.json'

export const LANGUAGES: Language[] = ['ar', 'fr', 'en']
const STORAGE_KEY = 'rafiq.language'

function isLanguage(value: unknown): value is Language {
  return typeof value === 'string' && (LANGUAGES as string[]).includes(value)
}

function detectLanguage(): Language {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (isLanguage(stored)) return stored
  } catch {
    // Storage unavailable (private mode): fall through to the browser language.
  }
  const browser = navigator.language.slice(0, 2)
  return isLanguage(browser) ? browser : 'en'
}

function applyDocumentLanguage(language: string) {
  document.documentElement.lang = language
  document.documentElement.dir = i18n.dir(language)
}

i18n.on('languageChanged', (language) => {
  applyDocumentLanguage(language)
  try {
    localStorage.setItem(STORAGE_KEY, language)
  } catch {
    // Non-essential preference.
  }
})

void i18n.use(initReactI18next).init({
  resources: { ar: { translation: ar }, fr: { translation: fr }, en: { translation: en } },
  lng: detectLanguage(),
  fallbackLng: 'en',
  supportedLngs: LANGUAGES,
  interpolation: { escapeValue: false }, // React already escapes
})

export function currentLanguage(): Language {
  return isLanguage(i18n.resolvedLanguage) ? i18n.resolvedLanguage : 'en'
}

export default i18n
