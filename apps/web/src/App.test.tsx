import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import App from '@/App'
import { sseEvent, streamResponse } from '@/test/sse'

const CONVERSATION_ID = '6f1c2f0e-8a8e-4c41-9d55-1b2f6a1a7c10'

function mockApi() {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
    const url = String(input)
    if (url === '/api/health') return Response.json({ status: 'ok', database: 'ok' })
    if (url === '/api/chat') {
      return streamResponse([
        sseEvent('meta', { conversation_id: CONVERSATION_ID, user_message_id: 1 }),
        sseEvent('delta', { text: 'Bonjour, ' }),
        sseEvent('delta', { text: 'comment puis-je aider ?' }),
        sseEvent('done', {
          message_id: 2,
          model: 'fake',
          usage: { input_tokens: 1, output_tokens: 1 },
        }),
      ])
    }
    return new Response('not found', { status: 404 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderApp() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

describe('App', () => {
  it('switches to Arabic with a right-to-left layout', async () => {
    mockApi()
    renderApp()

    await userEvent.click(screen.getByRole('button', { name: 'عربي' }))

    expect(document.documentElement.dir).toBe('rtl')
    expect(document.documentElement.lang).toBe('ar')
    expect(screen.getByRole('heading', { name: 'مرحبًا، أنا رفيق' })).toBeInTheDocument()
    expect(localStorage.getItem('rafiq.language')).toBe('ar')
  })

  it('streams the assistant reply and remembers the conversation', async () => {
    const fetchMock = mockApi()
    renderApp()

    await userEvent.type(screen.getByRole('textbox'), 'Bonjour{Enter}')

    expect(await screen.findByText('Bonjour, comment puis-je aider ?')).toBeInTheDocument()
    expect(screen.getByText('Bonjour')).toBeInTheDocument()
    expect(localStorage.getItem('rafiq.conversationId')).toBe(CONVERSATION_ID)

    const [, init] = fetchMock.mock.calls.find(([url]) => url === '/api/chat') ?? []
    const body = JSON.parse(String(init?.body))
    expect(body).toEqual({ message: 'Bonjour', language: 'en', conversation_id: null })
  })

  it('shows an error when the reply fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) =>
        String(input) === '/api/chat'
          ? streamResponse([
              sseEvent('meta', { conversation_id: CONVERSATION_ID, user_message_id: 1 }),
              sseEvent('error', { message: 'unavailable' }),
            ])
          : Response.json({ status: 'ok', database: 'ok' }),
      ),
    )
    renderApp()

    await userEvent.type(screen.getByRole('textbox'), 'Hello{Enter}')

    await waitFor(() =>
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Something went wrong. Please try again.',
      ),
    )
  })
})

describe('stale conversation', () => {
  it('starts a new conversation when the stored one no longer exists', async () => {
    localStorage.setItem('rafiq.conversationId', 'deleted-conversation')
    const fetchMock = mockApi() // GET /api/conversations/... falls through to 404
    renderApp()

    await screen.findByRole('heading', { name: "Hi, I'm Rafiq" })
    await userEvent.type(screen.getByRole('textbox'), 'Bonjour{Enter}')
    await screen.findByText('Bonjour, comment puis-je aider ?')

    const [, init] = fetchMock.mock.calls.find(([url]) => url === '/api/chat') ?? []
    expect(JSON.parse(String(init?.body)).conversation_id).toBeNull()
  })
})

describe('booking', () => {
  it('shows tool activity, then a card whose Confirm button books the appointment', async () => {
    const pendingCard = {
      action_id: 'action-1',
      kind: 'book',
      status: 'pending',
      expires_at: '2026-10-21T08:15:00Z',
      result: null,
      details: {
        doctor: 'Dr Amira Ben Salah',
        specialty: 'cardiology',
        starts_at: '2026-10-23T10:00:00+01:00',
        patient_name: 'Salma Ben Ali',
        patient_phone: '+216•••••123',
      },
    }
    let releaseFirstReply: () => void = () => {}
    const firstReplyReleased = new Promise<void>((resolve) => (releaseFirstReply = resolve))
    const chatBodies: unknown[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input) !== '/api/chat') return Response.json({ status: 'ok', database: 'ok' })
        chatBodies.push(JSON.parse(String(init?.body)))
        if (chatBodies.length === 1) {
          const encoder = new TextEncoder()
          const body = new ReadableStream<Uint8Array>({
            async start(controller) {
              controller.enqueue(
                encoder.encode(
                  sseEvent('meta', { conversation_id: CONVERSATION_ID, user_message_id: 1 }) +
                    sseEvent('tool', { id: 't1', name: 'check_availability', status: 'running' }),
                ),
              )
              await firstReplyReleased
              controller.enqueue(
                encoder.encode(
                  sseEvent('tool', { id: 't1', name: 'check_availability', status: 'done' }) +
                    sseEvent('confirmation', pendingCard) +
                    sseEvent('delta', { text: 'Please press Confirm.' }) +
                    sseEvent('done', { message_id: 2, model: 'm', usage: {} }),
                ),
              )
              controller.close()
            },
          })
          return new Response(body, { headers: { 'content-type': 'text/event-stream' } })
        }
        return streamResponse([
          sseEvent('meta', { conversation_id: CONVERSATION_ID, user_message_id: 3 }),
          sseEvent('action_result', {
            action_id: 'action-1',
            kind: 'book',
            decision: 'confirm',
            status: 'confirmed',
            booking_code: 'RFQ-7K3PX',
          }),
          sseEvent('delta', { text: 'Booked! Your code is RFQ-7K3PX.' }),
          sseEvent('done', { message_id: 4, model: 'm', usage: {} }),
        ])
      }),
    )
    renderApp()

    await userEvent.type(screen.getByRole('textbox'), 'Cardiologist on Friday{Enter}')
    expect(await screen.findByText('Checking availability…')).toBeInTheDocument()
    releaseFirstReply()

    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }))

    expect(await screen.findByText('Booked! Your code is RFQ-7K3PX.')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('ConfirmedRFQ-7K3PX')
    expect(chatBodies[1]).toEqual({
      message: 'Confirm',
      language: 'en',
      conversation_id: CONVERSATION_ID,
      action: { id: 'action-1', decision: 'confirm' },
    })
  })
})
