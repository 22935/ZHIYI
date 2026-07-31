/** Extract an SSE data field while accepting the optional space allowed after `data:`. */
export function parseSseDataLine(line: string): string | null {
  const normalized = line.endsWith('\r') ? line.slice(0, -1) : line
  if (!normalized.startsWith('data:')) return null

  const value = normalized.slice('data:'.length)
  return value.startsWith(' ') ? value.slice(1) : value
}

export type ChatStreamEventType =
  | 'reasoning_start'
  | 'reasoning_delta'
  | 'reasoning_end'
  | 'content_delta'
  | 'tool_start'
  | 'tool_result'
  | 'tool_error'
  | 'usage'
  | 'done'
  | 'error'

export interface ChatStreamEvent {
  event: ChatStreamEventType
  requestId: string
  sequence: number
  data: Record<string, any>
}

export function parseChatStreamData(data: string): ChatStreamEvent | null {
  if (data === '[DONE]') {
    return { event: 'done', requestId: 'legacy', sequence: 0, data: { status: 'completed' } }
  }
  try {
    const parsed = JSON.parse(data) as Record<string, any>
    if (typeof parsed.event === 'string' && parsed.data && typeof parsed.data === 'object') {
      return {
        event: parsed.event as ChatStreamEventType,
        requestId: typeof parsed.requestId === 'string' ? parsed.requestId : 'unknown',
        sequence: typeof parsed.sequence === 'number' ? parsed.sequence : 0,
        data: parsed.data
      }
    }
    if (typeof parsed.delta === 'string') {
      return {
        event: 'content_delta',
        requestId: 'legacy',
        sequence: 0,
        data: { delta: parsed.delta }
      }
    }
    if (parsed.error) {
      return {
        event: 'error',
        requestId: 'legacy',
        sequence: 0,
        data: { code: parsed.error }
      }
    }
  } catch {
    return null
  }
  return null
}
