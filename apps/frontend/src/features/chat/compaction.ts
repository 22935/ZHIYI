export interface ContextMessage { role: 'user' | 'assistant'; content: string }
export interface ContextCheckpoint { source: ContextMessage[]; projected: ContextMessage[]; modelKey: string }

/** Same conservative text allowance as the host/worker; never Provider usage.
 * Property order matches their canonical JSON wire format.
 */
export function estimateContextInput(source: ContextMessage[], fixedTokens: number): number {
  const encoder = new TextEncoder()
  return fixedTokens + source.reduce((total, item) => total
    + encoder.encode(JSON.stringify({ content: item.content, role: item.role })).length + 24, 0)
}

export function compactionFailureMessage(code: unknown): string {
  if (code === 'SUMMARY_PROVIDER_FAILED') return '摘要模型调用失败，原上下文已保留。请检查模型服务后重试。'
  if (['SUMMARY_INVALID_JSON', 'SUMMARY_INVALID_SCHEMA', 'SUMMARY_EMPTY'].includes(String(code))) {
    return '摘要模型未返回有效的结构化摘要，原上下文已保留。可以稍后重试。'
  }
  if (code === 'SUMMARY_TOO_LARGE') return '摘要超过压缩预算，原上下文已保留。可以稍后重试。'
  return '本次摘要未通过压缩校验，继续使用原上下文。可以稍后重试。'
}

/** Match the normal Chat Runtime: omit unfinished replies, trim plain-text history. */
export function conversationInput(messages: Array<{
  role: string; content: string; streamError?: string; thinkingState?: string; streamActivity?: string
}>): ContextMessage[] {
  return messages.filter(item => ['user', 'assistant'].includes(item.role) && item.content.trim()
    && !(item.role === 'assistant' && (item.streamError || item.thinkingState === 'error'
      || item.streamActivity === 'receiving' || item.streamActivity === 'waiting')))
    .map(item => ({ role: item.role as ContextMessage['role'], content: item.content.trim() }))
}

/** Reuse only an unchanged source prefix for this conversation and model settings. */
export function projectedInput(checkpoint: ContextCheckpoint | undefined, source: ContextMessage[], modelKey: string): ContextMessage[] | undefined {
  if (!checkpoint || checkpoint.modelKey !== modelKey || checkpoint.source.length > source.length
    || checkpoint.source.some((item, i) => item.role !== source[i].role || item.content !== source[i].content)) return
  return [...checkpoint.projected.map(item => ({ ...item })), ...source.slice(checkpoint.source.length)]
}
