import { useQuery } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'

import {
  ApiError,
  getConversation,
  streamChat,
  type ActionStatus,
  type Confirmation,
  type Decision,
  type Language,
  type MessageDTO,
  type Role,
  type Source,
  type ToolActivity,
} from '@/lib/api'

/** A card as shown: the server's status, or 'submitting' while a button press is in flight. */
export type CardState = Omit<Confirmation, 'status'> & { status: ActionStatus | 'submitting' }

export interface UiMessage {
  id: string
  role: Role
  content: string
  sources: Source[]
  tools: ToolActivity[]
  confirmation: CardState | null
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

function fromDTO(m: MessageDTO): UiMessage {
  return {
    id: String(m.id),
    role: m.role,
    content: m.content,
    sources: m.sources ?? [],
    tools: [],
    confirmation: m.confirmation,
    status: 'done',
  }
}

function newMessage(role: Role, content: string, status: UiMessage['status']): UiMessage {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    sources: [],
    tools: [],
    confirmation: null,
    status,
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

  const restored: UiMessage[] = history.data?.messages.map(fromDTO) ?? []
  const messages = live ?? restored

  useEffect(() => () => abortRef.current?.abort(), [])

  const updateCards = (update: (card: CardState) => CardState) =>
    setLive((prev) =>
      (prev ?? restored).map((m) =>
        m.confirmation ? { ...m, confirmation: update(m.confirmation) } : m,
      ),
    )

  async function send(text: string, action?: { id: string; decision: Decision }) {
    const message = text.trim()
    if (!message || isStreaming) return

    const controller = new AbortController()
    abortRef.current = controller
    const assistant = newMessage('assistant', '', 'streaming')
    const updateAssistant = (update: (m: UiMessage) => UiMessage) =>
      setLive((prev) => (prev ?? []).map((m) => (m.id === assistant.id ? update(m) : m)))

    setLive((prev) => [...(prev ?? restored), newMessage('user', message, 'done'), assistant])
    setIsStreaming(true)

    let finished = false
    try {
      for await (const event of streamChat(
        { message, language, conversationId: activeConversationId, action },
        controller.signal,
      )) {
        switch (event.type) {
          case 'meta':
            setConversationId(event.conversationId)
            storeId(event.conversationId)
            break
          case 'action_result':
            updateCards((card) =>
              card.action_id === event.result.action_id
                ? {
                    ...card,
                    status: event.result.status,
                    result: { booking_code: event.result.booking_code, error: event.result.error },
                  }
                : card,
            )
            break
          case 'sources':
            updateAssistant((m) => ({ ...m, sources: event.sources }))
            break
          case 'delta':
            updateAssistant((m) => ({ ...m, content: m.content + event.text }))
            break
          case 'tool':
            updateAssistant((m) => ({
              ...m,
              tools: [...m.tools.filter((t) => t.id !== event.tool.id), event.tool],
            }))
            break
          case 'confirmation':
            // Only the newest card in a chat stays valid (the server supersedes older ones).
            updateCards((card) =>
              card.status === 'pending' ? { ...card, status: 'superseded' } : card,
            )
            updateAssistant((m) => ({ ...m, confirmation: event.confirmation }))
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

  /** The patient pressed Confirm or Cancel on a card; `label` is shown as their message. */
  async function respond(card: CardState, decision: Decision, label: string) {
    if (isStreaming || card.status !== 'pending') return
    updateCards((c) => (c.action_id === card.action_id ? { ...c, status: 'submitting' } : c))
    await send(label, { id: card.action_id, decision })
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
    respond,
    stop,
    reset,
  }
}

export type ChatController = ReturnType<typeof useChat>
