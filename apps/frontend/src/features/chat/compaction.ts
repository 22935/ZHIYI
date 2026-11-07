export interface ContextMessage { role: 'user' | 'assistant'; content: string }
export interface ContextCheckpoint { source: ContextMessage[]; projected: ContextMessage[]; modelKey: string }

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
