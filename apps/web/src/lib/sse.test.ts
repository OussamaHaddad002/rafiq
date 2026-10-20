import { describe, expect, it } from 'vitest'

import { streamResponse } from '@/test/sse'
import { readSSE, type SSEMessage } from './sse'

async function collect(chunks: string[]): Promise<SSEMessage[]> {
  const messages: SSEMessage[] = []
  for await (const message of readSSE(streamResponse(chunks).body!)) messages.push(message)
  return messages
}

describe('readSSE', () => {
  it('parses named events', async () => {
    expect(await collect(['event: delta\ndata: {"text":"hi"}\n\n'])).toEqual([
      { event: 'delta', data: '{"text":"hi"}' },
    ])
  })

  it('reassembles events split across chunks', async () => {
    const messages = await collect([
      'event: del',
      'ta\ndata: {"te',
      'xt":"a"}\n',
      '\nevent: done\ndata: {}\n\n',
    ])
    expect(messages.map((m) => m.event)).toEqual(['delta', 'done'])
    expect(messages[0].data).toBe('{"text":"a"}')
  })

  it('decodes multi-byte characters split across chunks', async () => {
    const bytes = new TextEncoder().encode('data: "مرحبا"\n\n')
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(bytes.slice(0, 9)) // cuts an Arabic character in half
        controller.enqueue(bytes.slice(9))
        controller.close()
      },
    })
    const messages: SSEMessage[] = []
    for await (const message of readSSE(body)) messages.push(message)
    expect(messages).toEqual([{ event: 'message', data: '"مرحبا"' }])
  })

  it('ignores keep-alive comments and handles CRLF', async () => {
    expect(await collect([': ping\r\n\r\n', 'event: done\r\ndata: 1\r\n\r\n'])).toEqual([
      { event: 'done', data: '1' },
    ])
  })

  it('joins multi-line data', async () => {
    expect(await collect(['data: a\ndata: b\n\n'])).toEqual([{ event: 'message', data: 'a\nb' }])
  })
})
