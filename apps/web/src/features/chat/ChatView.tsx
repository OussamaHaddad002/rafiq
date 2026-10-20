import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'

import { Composer } from './Composer'
import { EmptyState } from './EmptyState'
import { MessageBubble } from './MessageBubble'
import type { ChatController } from './useChat'

export function ChatView({ chat }: { chat: ChatController }) {
  const { t } = useTranslation()
  const endRef = useRef<HTMLDivElement>(null)
  const lastMessage = chat.messages.at(-1)

  // Follow the reply as it streams in.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' })
  }, [chat.messages.length, lastMessage?.content])

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col">
      <div className="flex flex-1 flex-col overflow-y-auto px-4">
        {chat.messages.length === 0 && !chat.isRestoring ? (
          <EmptyState onPick={(text) => void chat.send(text)} />
        ) : (
          <div className="flex flex-col gap-5 py-6">
            {chat.messages.map((message) => (
              <MessageBubble key={message.id} message={message} />
            ))}
            <div ref={endRef} />
          </div>
        )}
      </div>
      <div className="px-4 pb-4">
        <Composer
          isStreaming={chat.isStreaming}
          onSend={(text) => void chat.send(text)}
          onStop={chat.stop}
        />
        <p className="mt-2 text-center text-xs text-muted-foreground">{t('chat.disclaimer')}</p>
      </div>
    </div>
  )
}
