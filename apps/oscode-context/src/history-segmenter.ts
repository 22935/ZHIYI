/** Adapted DSH region.ts/tool-pairing.ts. OScode checks actual IDs, not just a
 * count balance. Session surface events are replaced by immutable SDK input.
 */
import { CompactionError } from './contracts.ts'
import type { Message } from './contracts.ts'
import type { TokenMeter } from './token-meter.ts'

export function toolCalls(item: Message): string[] {
  if (item.type === 'function_call') return [String(item.call_id || '')]
  return (item.tool_calls || []).map((call: any) => String(call.id || ''))
}
export function resultId(item: Message): string | undefined {
  if (item.type === 'function_call_output') return String(item.call_id || '')
  if (item.role === 'tool') return String(item.tool_call_id || '')
}
export function balancedCuts(messages: Message[]): boolean[] {
  const pending = new Set<string>(), seen = new Set<string>(), cuts = [true]
  for (const item of messages) {
    for (const id of toolCalls(item)) {
      if (!id || seen.has(id)) throw new CompactionError('Duplicate or missing tool call ID')
      pending.add(id); seen.add(id)
    }
    const id = resultId(item)
    if (id !== undefined) {
      if (!pending.delete(id)) throw new CompactionError('Orphan or duplicate tool result')
    }
    cuts.push(pending.size === 0)
  }
  return cuts
}
export function protectedItem(item: Message): boolean {
  if (['system', 'developer'].includes(item.role)) return true
  if (Array.isArray(item.content) && item.content.some((b: any) => !['text', 'input_text', 'output_text'].includes(b.type))) return true
  return !['message', 'function_call', 'function_call_output', 'reasoning'].includes(item.type || 'message')
}
export function selectRange(messages: Message[], meter: TokenMeter, retainTurns: number, retainTokens: number): [number, number] | undefined {
  const cuts = balancedCuts(messages)
  const users = messages.flatMap((m, i) => m.role === 'user' ? [i] : [])
  if (users.length <= retainTurns) return
  let keep = users[users.length - retainTurns]
  let accumulated = meter.messages(messages.slice(keep))
  while (keep > 0 && accumulated < retainTokens) accumulated += meter.message(messages[--keep])
  // Round toward the older head to preserve a complete turn and tool cycle.
  while (keep > 0 && (!cuts[keep] || messages[keep].role !== 'user')) keep--
  let start = 0
  while (start < keep && protectedItem(messages[start])) start++
  let end = keep
  for (let i = start; i < keep; i++) if (protectedItem(messages[i])) { end = i; break }
  while (end > start && !cuts[end]) end--
  if (start < end && cuts[start]) return [start, end]
}
