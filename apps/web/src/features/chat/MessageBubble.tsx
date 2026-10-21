import { HeartPulse } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/utils'
import { CitedText, SourceList } from './Citations'
import { citedNumbers } from './citationMarkers'
import type { UiMessage } from './useChat'

export function MessageBubble({ message }: { message: UiMessage }) {
  const { t } = useTranslation()
  const isUser = message.role === 'user'
  const isWaiting = message.status === 'streaming' && message.content === ''
  const [activeSource, setActiveSource] = useState<number | null>(null)
  const toggleSource = (n: number) => setActiveSource((current) => (current === n ? null : n))

  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse')}>
      {!isUser && (
        <div
          aria-hidden
          className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"
        >
          <HeartPulse className="size-4" />
        </div>
      )}
      <div className={cn('flex max-w-[85%] flex-col gap-1', isUser && 'items-end')}>
        <span className="sr-only">{isUser ? t('chat.you') : t('chat.assistant')}</span>
        {isWaiting ? (
          <TypingDots />
        ) : (
          <div
            // dir="auto" lets an Arabic message render RTL inside a French UI, and vice versa.
            dir="auto"
            className={cn(
              'rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed whitespace-pre-wrap break-words',
              isUser
                ? 'rounded-ee-sm bg-primary text-primary-foreground'
                : 'rounded-ss-sm border bg-card',
            )}
          >
            {isUser ? (
              message.content
            ) : (
              <CitedText
                text={message.content}
                sources={message.sources}
                active={activeSource}
                onCite={toggleSource}
              />
            )}
            {message.status === 'streaming' && (
              <span className="ms-0.5 inline-block h-4 w-0.5 translate-y-0.5 animate-pulse bg-current" />
            )}
          </div>
        )}
        {!isUser && (
          <SourceList
            sources={message.sources}
            cited={citedNumbers(message.content, message.sources)}
            active={activeSource}
            onToggle={toggleSource}
          />
        )}
        {message.status === 'error' && (
          <p role="alert" className="px-1 text-sm text-destructive">
            {t('chat.error')}
          </p>
        )}
      </div>
    </div>
  )
}

function TypingDots() {
  return (
    <div className="flex h-10 items-center gap-1 rounded-2xl rounded-ss-sm border bg-card px-4">
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          className="size-1.5 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: `${delay}ms` }}
        />
      ))}
    </div>
  )
}
