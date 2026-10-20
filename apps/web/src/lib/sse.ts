export interface SSEMessage {
  event: string
  data: string
}

/**
 * Parses a `text/event-stream` body into messages.
 * Used instead of EventSource because EventSource cannot send POST requests.
 */
export async function* readSSE(body: ReadableStream<Uint8Array>): AsyncGenerator<SSEMessage> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer = (buffer + decoder.decode(value, { stream: true })).replace(/\r\n/g, '\n')
      let boundary: number
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const message = parseBlock(buffer.slice(0, boundary))
        buffer = buffer.slice(boundary + 2)
        if (message) yield message
      }
    }
  } finally {
    reader.cancel().catch(() => undefined)
  }
}

function parseBlock(block: string): SSEMessage | null {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line === '' || line.startsWith(':')) continue // keep-alive comments
    const colon = line.indexOf(':')
    const field = colon === -1 ? line : line.slice(0, colon)
    let value = colon === -1 ? '' : line.slice(colon + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    else if (field === 'data') data.push(value)
  }
  return data.length > 0 ? { event, data: data.join('\n') } : null
}
