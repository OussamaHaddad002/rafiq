import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import { ApiError, getConversation, streamChat, type Language, type Role } from '@/lib/api'

export interface UiMessage {
  id: string
  role: Role
  content: string
  status: 'done' | 'streaming' | 'error'
}

const STORAGE_KEY = 'rafiq.conversationId'

function readStoredId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function storeId(id: string | null) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    // Losing the conversation on reload is acceptable.
  }
}

export function useChat(language: Language) {
  const [conversationId, setConversationId] = useState<string | null>(readStoredId)
  // null until something is sent in this session; until then we show the restored history.
  const [live, setLive] = useState<UiMessage[] | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const history = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: async () => {
      try {
        return await getConversation(conversationId as string)
      } catch (error) {
        // A stored conversation that no longer exists (e.g. demo DB reset): start fresh.
        if (error instanceof ApiError && error.status === 404) {
          storeId(null)
          return null
        }
        throw error
      }
    },
    enabled: conversationId !== null && live === null,
    retry: false,
    staleTime: Infinity,
  })
  const activeConversationId = history.data === null ? null : conversationId

  const restored: UiMessage[] =
    history.data?.messages.map((m) => ({
      id: String(m.id),
      role: m.role,
      content: m.content,
      status: 'done',
    })) ?? []
  const messages = live ?? restored

  useEffect(() => () => abortRef.current?.abort(), [])

  async function send(text: string) {
    const message = text.trim()
    if (!message || isStreaming) return

    const controller = new AbortController()
    abortRef.current = controller
    const assistantId = crypto.randomUUID()
    const updateAssistant = (update: (m: UiMessage) => UiMessage) =>
      setLive((prev) => (prev ?? []).map((m) => (m.id === assistantId ? update(m) : m)))

    setLive((prev) => [
      ...(prev ?? restored),
      { id: crypto.randomUUID(), role: 'user', content: message, status: 'done' },
      { id: assistantId, role: 'assistant', content: '', status: 'streaming' },
    ])
    setIsStreaming(true)

    let finished = false
    try {
      for await (const event of streamChat(
        { message, language, conversationId: activeConversationId },
        controller.signal,
      )) {
        switch (event.type) {
          case 'meta':
            setConversationId(event.conversationId)
            storeId(event.conversationId)
            break
          case 'delta':
            updateAssistant((m) => ({ ...m, content: m.content + event.text }))
            break
          case 'done':
            finished = true
            updateAssistant((m) => ({ ...m, status: 'done' }))
            break
          case 'error':
            finished = true
            updateAssistant((m) => ({ ...m, status: 'error' }))
            break
        }
      }
      if (!finished) updateAssistant((m) => ({ ...m, status: 'error' })) // connection dropped
    } catch (error) {
      if (controller.signal.aborted) {
        updateAssistant((m) => ({ ...m, status: 'done' })) // stopped by the user: keep partial text
      } else {
        if (error instanceof ApiError && error.status === 404) {
          storeId(null)
          setConversationId(null)
        }
        updateAssistant((m) => ({ ...m, status: 'error' }))
      }
    } finally {
      setIsStreaming(false)
      abortRef.current = null
    }
  }

  function stop() {
    abortRef.current?.abort()
  }

  function reset() {
    abortRef.current?.abort()
    storeId(null)
    setConversationId(null)
    setLive([])
  }

  return {
    messages,
    isStreaming,
    isRestoring: history.isLoading,
    send,
    stop,
    reset,
  }
}

export type ChatController = ReturnType<typeof useChat>
