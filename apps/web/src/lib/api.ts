import { readSSE } from '@/lib/sse'

export type Language = 'ar' | 'fr' | 'en'
export type Role = 'user' | 'assistant'

/** A knowledge-base excerpt given to the model; `n` is its citation number, as in [n]. */
export interface Source {
  n: number
  source: string
  title: string
  page: number | null
  section: string | null
  lang: string
  excerpt: string
}

export type ActionKind = 'book' | 'reschedule' | 'cancel'
export type ActionStatus =
  'pending' | 'confirmed' | 'declined' | 'expired' | 'failed' | 'superseded'
export type Decision = 'confirm' | 'decline'

/** What a Confirm / Cancel card shows. Times are ISO strings with the clinic's UTC offset. */
export interface ActionDetails {
  doctor: string
  specialty: string
  starts_at: string
  previous_starts_at?: string
  patient_name: string
  patient_phone: string
  booking_code?: string
  late_cancellation_fee_dt?: number
}

export interface Confirmation {
  action_id: string
  kind: ActionKind
  status: ActionStatus
  details: ActionDetails
  expires_at: string
  result: { booking_code?: string; error?: string; message?: string } | null
}

export interface ActionResult {
  action_id: string
  kind: ActionKind
  decision: Decision
  status: ActionStatus
  booking_code?: string
  error?: string
  message?: string
}

export interface ToolActivity {
  id: string
  name: string
  status: 'running' | 'done' | 'error'
}

export interface MessageDTO {
  id: number
  role: Role
  content: string
  sources: Source[] | null
  confirmation: Confirmation | null
  action_result: ActionResult | null
  created_at: string
}

export interface ConversationDTO {
  id: string
  language: Language
  created_at: string
  messages: MessageDTO[]
}

export interface HealthDTO {
  status: 'ok' | 'degraded'
  database: 'ok' | 'unavailable'
}

export interface Usage {
  input_tokens: number
  output_tokens: number
}

export type ChatStreamEvent =
  | { type: 'meta'; conversationId: string; userMessageId: number }
  | { type: 'action_result'; result: ActionResult }
  | { type: 'sources'; sources: Source[] }
  | { type: 'delta'; text: string }
  | { type: 'tool'; tool: ToolActivity }
  | { type: 'confirmation'; confirmation: Confirmation }
  | { type: 'done'; messageId: number; model: string; usage: Usage }
  | { type: 'error'; message: string }

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function errorFrom(response: Response): Promise<ApiError> {
  let detail = response.statusText
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      detail = body.detail
    }
  } catch {
    // Non-JSON error body: keep the status text.
  }
  return new ApiError(response.status, detail)
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { headers: { accept: 'application/json' } })
  if (!response.ok) throw await errorFrom(response)
  return (await response.json()) as T
}

export const getHealth = () => getJson<HealthDTO>('/api/health')

export const getConversation = (id: string) =>
  getJson<ConversationDTO>(`/api/conversations/${encodeURIComponent(id)}`)

export interface ChatRequest {
  message: string
  language: Language
  conversationId: string | null
  /** Set when the message is the patient pressing Confirm / Cancel on a card. */
  action?: { id: string; decision: Decision }
}

export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'content-type': 'application/json', accept: 'text/event-stream' },
    body: JSON.stringify({
      message: request.message,
      language: request.language,
      conversation_id: request.conversationId,
      ...(request.action ? { action: request.action } : {}),
    }),
    signal,
  })
  if (!response.ok || !response.body) throw await errorFrom(response)

  for await (const { event, data } of readSSE(response.body)) {
    const payload = JSON.parse(data)
    switch (event) {
      case 'meta':
        yield {
          type: 'meta',
          conversationId: payload.conversation_id,
          userMessageId: payload.user_message_id,
        }
        break
      case 'action_result':
        yield { type: 'action_result', result: payload }
        break
      case 'sources':
        yield { type: 'sources', sources: payload }
        break
      case 'delta':
        yield { type: 'delta', text: payload.text }
        break
      case 'tool':
        yield { type: 'tool', tool: payload }
        break
      case 'confirmation':
        yield { type: 'confirmation', confirmation: payload }
        break
      case 'done':
        yield {
          type: 'done',
          messageId: payload.message_id,
          model: payload.model,
          usage: payload.usage,
        }
        break
      case 'error':
        yield { type: 'error', message: payload.message }
        break
    }
  }
}
