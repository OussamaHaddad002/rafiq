import { HeartPulse } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  const { t } = useTranslation()
  const suggestions = t('chat.suggestions', { returnObjects: true })

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-6 px-4 py-10 text-center">
      <div className="flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <HeartPulse className="size-7" />
      </div>
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold tracking-tight">{t('chat.emptyTitle')}</h2>
        <p className="mx-auto max-w-md text-muted-foreground">{t('chat.emptyBody')}</p>
      </div>
      <ul className="flex max-w-xl flex-wrap justify-center gap-2">
        {suggestions.map((suggestion) => (
          <li key={suggestion}>
            <button
              type="button"
              dir="auto"
              onClick={() => onPick(suggestion)}
              className="rounded-full border bg-card px-4 py-2 text-sm transition-colors hover:border-primary/50 hover:bg-primary/5"
            >
              {suggestion}
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
