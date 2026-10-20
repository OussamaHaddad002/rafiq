import { SquarePen } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { HealthIndicator } from '@/components/HealthIndicator'
import { LanguageSwitcher } from '@/components/LanguageSwitcher'
import { Button } from '@/components/ui/button'
import { ChatView } from '@/features/chat/ChatView'
import { useChat } from '@/features/chat/useChat'
import { currentLanguage } from '@/i18n'

export default function App() {
  const { t } = useTranslation()
  const chat = useChat(currentLanguage())

  return (
    <div className="flex h-full flex-col">
      <header className="border-b bg-card/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-3xl items-center gap-3 px-4">
          <img src="/favicon.svg" alt="" className="size-8" />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <h1 className="font-semibold">{t('app.name')}</h1>
              <HealthIndicator />
            </div>
            <p className="truncate text-xs text-muted-foreground">{t('app.tagline')}</p>
          </div>
          <LanguageSwitcher />
          <Button
            variant="ghost"
            size="icon"
            onClick={chat.reset}
            disabled={chat.messages.length === 0}
            aria-label={t('app.newChat')}
            title={t('app.newChat')}
          >
            <SquarePen />
          </Button>
        </div>
      </header>
      <main className="min-h-0 flex-1">
        <ChatView chat={chat} />
      </main>
    </div>
  )
}
