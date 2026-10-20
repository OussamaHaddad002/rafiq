/** Builds a streaming Response whose body arrives in the given chunks. */
export function streamResponse(chunks: string[], init?: ResponseInit): Response {
  const encoder = new TextEncoder()
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk))
      controller.close()
    },
  })
  return new Response(body, { headers: { 'content-type': 'text/event-stream' }, ...init })
}

export function sseEvent(event: string, data: unknown): string {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`
}
