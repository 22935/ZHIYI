/** Extract an SSE data field while accepting the optional space allowed after `data:`. */
export function parseSseDataLine(line: string): string | null {
  const normalized = line.endsWith('\r') ? line.slice(0, -1) : line
  if (!normalized.startsWith('data:')) return null

  const value = normalized.slice('data:'.length)
  return value.startsWith(' ') ? value.slice(1) : value
}

export type ChatStreamEventType =
  | 'heartbeat'
  | 'reasoning_start'
  | 'reasoning_delta'
  | 'reasoning_end'
  | 'content_delta'
  | 'tool_start'
  | 'tool_result'
  | 'tool_error'
  | 'approval_required'
  | 'approval_resolved'
  | 'execution_started'
  | 'stdout_delta'
  | 'stderr_delta'
  | 'execution_completed'
  | 'execution_failed'
  | 'execution_cancelled'
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

/** Keep the SSE event field: gateway terminal events have no JSON envelope. */
export function parseChatStreamFrame(frame: string): ChatStreamEvent | null {
  let eventName = ''
  const data: string[] = []
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith('event:')) eventName = line.slice(6).trim()
    const value = parseSseDataLine(line)
    if (value !== null) data.push(value)
  }
  if (!data.length) return null
  const payload = data.join('\n')
  if (eventName === 'error') {
    try {
      const parsed = JSON.parse(payload)
      if (!parsed.event) {
        const data: Record<string, any> = { code: parsed.code || parsed.error || 'AI_STREAM_FAILED' }
        if (typeof parsed.message === 'string' && parsed.message) data.message = parsed.message
        if (typeof parsed.retryable === 'boolean') data.retryable = parsed.retryable
        return { event: eventName, requestId: 'unknown', sequence: 0, data }
      }
    } catch { return null }
  }
  return parseChatStreamData(payload)
}

const STREAM_ERROR_MESSAGES: Record<string, string> = {
  SSE_IDLE_TIMEOUT: '等待模型响应超时，请重试',
  SSE_MAX_DURATION: '本次回复已达到最长生成时间，请重试',
  AI_STREAM_INTERRUPTED: '模型连接中断，请重试',
  AI_TURN_LIMIT_EXCEEDED: '本次回复达到工具轮数上限，请重试',
  AI_UPSTREAM_TIMEOUT: '模型响应超时，请重试',
  AI_UPSTREAM_UNREACHABLE: '无法连接模型服务，请检查网络或代理后重试',
  AI_UPSTREAM_REJECTED: '模型服务拒绝了本次请求，请重试',
  AI_CONTEXT_OVERFLOW: '上下文超出模型窗口，请缩短对话后重试'
}

export function chatStreamErrorMessage(code?: string, message?: string): string {
  const known = code ? STREAM_ERROR_MESSAGES[code] : undefined
  if (known) return known
  // Unknown code: prefer the server's fixed text, but keep the code visible so
  // a user can report it and the log line can be matched.
  if (message) return code ? `${message}（${code}）` : message
  return `回复生成失败，请重试${code ? `（${code}）` : ''}`
}
