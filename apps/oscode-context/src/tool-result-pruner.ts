/** DSH MIT pruneContent algorithm, framework shell removed. See provenance.json.
 * Text slicing uses Unicode code points; rich blocks keep their order.
 */
import type { Config, Message } from './contracts.ts'
import { CompactionError } from './contracts.ts'
import { resultId } from './history-segmenter.ts'
export const PRUNE_MARKER = '\n\n[... tool result middle pruned ...]\n\n'
type Block = Record<string, any>
export function pruneContent(blocks: Block[], config: Pick<Config, 'thresholdChars' | 'headChars' | 'tailChars'>): Block[] | undefined {
  const measure = (values: Block[]) => values.reduce((n, b) => n + (b.type === 'text' ? Array.from(b.text as string).length : 0), 0)
  const totalChars = measure(blocks)
  if (totalChars <= config.thresholdChars) return
  const removedStart = config.headChars, removedEnd = totalChars - config.tailChars
  const pruned: Block[] = []
  let consumed = 0, markerInserted = false
  for (const block of blocks) {
    if (block.type !== 'text') { pruned.push(block); continue }
    const points = Array.from(block.text as string)
    const blockStart = consumed, blockEnd = blockStart + points.length
    const headEnd = Math.min(points.length, Math.max(0, removedStart - blockStart))
    const tailStart = Math.min(points.length, Math.max(0, removedEnd - blockStart))
    const intersectsRemoved = blockStart < removedEnd && blockEnd > removedStart
    const marker = intersectsRemoved && !markerInserted ? PRUNE_MARKER : ''
    if (marker.length > 0) markerInserted = true
    const text = points.slice(0, headEnd).join('') + marker + points.slice(tailStart).join('')
    if (text.length > 0) pruned.push({ ...block, text })
    consumed = blockEnd
  }
  if (!markerInserted || measure(pruned) > config.thresholdChars || measure(pruned) >= totalChars) throw new CompactionError('Pruner failed to shrink within budget')
  return pruned
}
export function pruneResults(messages: Message[], config: Config, safeEnd: number): { messages: Message[]; removedChars: number } {
  const projected = structuredClone(messages)
  let removedChars = 0
  const text = (value: string): string => {
    const pruned = pruneContent([{ type: 'text', text: value }], config)
    if (!pruned) return value
    const replacement = pruned[0]?.text || ''
    removedChars += Array.from(value).length - Array.from(replacement as string).length
    return replacement
  }
  const visit = (value: any): any => {
    if (Array.isArray(value)) return value.map(visit)
    if (!value || typeof value !== 'object') return value
    // Rich/multimodal blocks are opaque: never shorten embedded image/file data.
    if (typeof value.type === 'string' && !['text', 'input_text', 'output_text'].includes(value.type)) return value
    if (value.error || value.isError || ['failed', 'error', 'denied'].includes(value.status)) return value
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k,
      ['stdout', 'stderr', 'output', 'text', 'content', 'body', 'snippet'].includes(k) && typeof v === 'string' ? text(v) : visit(v)]))
  }
  projected.forEach((item, i) => {
    if (i >= safeEnd || resultId(item) === undefined || item.is_error) return
    const key = item.type === 'function_call_output' ? 'output' : 'content'
    const value = item[key]
    if (typeof value === 'string') {
      let parsed: any
      try { parsed = JSON.parse(value) } catch {
        item[key] = /error|exception|failed/i.test(value) ? value : text(value); return
      }
      const next = visit(parsed)
      // Do not reserialize untouched JSON (including errors).
      if (JSON.stringify(next) !== JSON.stringify(parsed)) item[key] = JSON.stringify(next)
    } else item[key] = visit(value)
  })
  return { messages: projected, removedChars }
}
