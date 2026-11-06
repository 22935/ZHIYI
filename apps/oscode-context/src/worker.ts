/** Request-scoped JSON-lines worker. No HTTP server, credentials, tools or DB.
 * The Python host executes the existing tool-free Provider helper on summary RPC.
 */
import { createInterface } from 'node:readline'
import { ContextCompactionEngine } from './engine.ts'
import { modelMeter, wire } from './token-meter.ts'
import type { ProjectionRequest, Config } from './contracts.ts'

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity })
const send = (value: unknown) => process.stdout.write(wire(value) + '\n')
const pending = new Map<number, { resolve: (v: any) => void; reject: (e: Error) => void }>()
let sequence = 0, busy = false, engine: ContextCompactionEngine | undefined, owner: string | undefined
const invoke = (text: string, maxTokens: number, instruction: string) => new Promise<{ text: string; totalTokens?: number }>((resolve, reject) => {
  const id = ++sequence
  pending.set(id, { resolve, reject })
  send({ type: 'summarize', id, text, maxTokens, instruction })
})
lines.on('line', line => {
  let command: any
  try { command = JSON.parse(line) } catch { send({ type: 'error', code: 'INVALID_JSON' }); return }
  if (command.type === 'summary') {
    const waiting = pending.get(command.id)
    if (!waiting) { send({ type: 'error', code: 'UNEXPECTED_SUMMARY' }); return }
    pending.delete(command.id)
    if (command.error) waiting.reject(new Error('Summary Provider failed'))
    else waiting.resolve(command.result)
    return
  }
  if (command.type !== 'project' || busy) { send({ type: 'error', code: 'INVALID_COMMAND' }); return }
  busy = true
  void (async () => {
    try {
      const request = command.request as ProjectionRequest
      const nextOwner = wire([request.contextId, request.provider, request.model, command.config, command.tokenizer])
      // A worker is one Runner's context, not an arbitrary multi-session service.
      if (owner !== undefined && owner !== nextOwner) throw new Error('Worker owner changed')
      owner = nextOwner
      if (!engine) engine = new ContextCompactionEngine(await modelMeter(request.model, command.tokenizer), invoke, command.config as Partial<Config>)
      send({ type: 'result', projection: await engine.project(request) })
    } catch (error) {
      // No payloads or credentials in protocol errors.
      send({ type: 'error', code: error instanceof Error ? error.name : 'COMPACTION_FAILED' })
    } finally { busy = false }
  })()
})
lines.on('close', () => {
  for (const waiter of pending.values()) waiter.reject(new Error('Host closed'))
  pending.clear()
})
