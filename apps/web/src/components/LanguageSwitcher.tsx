import { useTranslation } from 'react-i18next'

import { LANGUAGES } from '@/i18n'
import type { Language } from '@/lib/api'
import { cn } from '@/lib/utils'

const LABELS: Record<Language, string> = { ar: 'عربي', fr: 'FR', en: 'EN' }

export function LanguageSwitcher() {
  const { t, i18n } = useTranslation()

  return (
    <div
      role="group"
      aria-label={t('app.language')}
      className="flex rounded-lg border bg-card p-0.5"
    >
      {LANGUAGES.map((language) => {
        const active = i18n.resolvedLanguage === language
        return (
          <button
            key={language}
            type="button"
            lang={language}
            aria-pressed={active}
            onClick={() => void i18n.changeLanguage(language)}
            className={cn(
              'rounded-md px-2.5 py-1 text-xs font-medium transition-colors',
              active
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {LABELS[language]}
          </button>
        )
      })}
    </div>
  )
}
