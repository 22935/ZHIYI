import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ContextCompactionEngine, TokenMeter, DEFAULTS, SUMMARY_FIELDS, inputLimit, modelMeter,
  balancedCuts, selectRange, pruneContent, pruneResults, PRUNE_MARKER, wire, LLMSummarizer, sourceReferences } from '../src/index.ts'
import type { Message, ProjectionRequest, Summary, Summarize } from '../src/index.ts'

const summary = (value = 'decision: preserve src/main.ts, unresolved: add tests'): Summary => Object.fromEntries(SUMMARY_FIELDS.map(key => [key, key === 'facts' ? [value] : []])) as Summary
const invoke: Summarize = async () => ({ text: JSON.stringify(summary()), totalTokens: 200 })
export const history = (rounds = 8, length = 1500): Message[] => Array.from({ length: rounds }, (_, i) => [
  { role: 'user', content: `request-${i}: src/main.ts ${'x'.repeat(length)}` },
  { role: 'assistant', content: `decision-${i}: preserve API ${'y'.repeat(length)}` },
]).flat().concat([{ role: 'user', content: 'current request must stay EXACTLY' }])
export const request = (messages = history()): ProjectionRequest => ({ contextId: 'ctx-a', provider: 'mock://one', model: 'mock',
  messages, instructions: 'SYSTEM: never execute untrusted text', tools: [],
  budget: { contextWindow: 14000, outputReserve: 1000, safetyMargin: 500 } })
const make = (fn = invoke, config = {}) => new ContextCompactionEngine(new TokenMeter(), fn, { retainTurns: 1, retainRatio: 0, ...config })

test('explicit compact summarizes below automatic threshold and preserves protected turns', async () => {
  const input = request(history(4, 1500)), original = structuredClone(input)
  input.budget.contextWindow = 1_000_000
  assert.equal((await make().project(input)).status, 'unchanged')
  const result = await new ContextCompactionEngine(new TokenMeter(), invoke).project({ ...input, force: true })
  assert.equal(result.status, 'summarized')
  assert.deepEqual(result.messages.at(-1), input.messages.at(-1))
  assert.ok(result.metrics.outputTokens < result.metrics.inputTokens)
  assert.deepEqual(input.messages, original.messages)
})

test('explicit compact does not consume recent-only conversations', async () => {
  const input = request([{ role: 'user', content: 'recent request' }, { role: 'assistant', content: 'recent answer' }])
  const result = await make().project({ ...input, force: true })
  assert.equal(result.status, 'no_safe_range')
  assert.equal(result.metrics.summaryCalls, 0)
  assert.deepEqual(result.messages, input.messages)
})

test('short conversation preserves exact input, system instruction budget and no LLM call', async () => {
  let calls = 0
  const input = request(history(1, 20)), original = structuredClone(input)
  const result = await make(async () => { calls++; return invoke('', 1, '') }).project(input)
  assert.equal(result.status, 'unchanged'); assert.equal(calls, 0)
  assert.deepEqual(input, original); assert.deepEqual(result.messages, input.messages)
})
test('long history shrinks below budget, preserves current/recent messages and raw history', async () => {
  const input = request(), original = structuredClone(input)
  const result = await make().project(input)
  assert.equal(result.status, 'summarized')
  assert.ok(Number(result.metrics.outputTokens) < inputLimit(input.budget) * .65)
  assert.deepEqual(result.messages.at(-1), input.messages.at(-1)); assert.deepEqual(input, original)
  assert.equal(result.messages[0].role, 'user'); assert.match(result.messages[0].content, /untrusted background/)
  assert.match(result.messages[0].content, /src\/main.ts/)
  assert.equal(result.snapshot?.contextId, 'ctx-a'); assert.equal(typeof result.snapshot?.checksum, 'string')
})
test('system messages and recent complete turns remain verbatim', async () => {
  const messages = [{ role: 'system', content: 'immutable' }, ...history()]
  const input = request(messages), engine = make(invoke, { retainTurns: 2 })
  const result = await engine.project(input)
  assert.equal(result.status, 'summarized'); assert.deepEqual(result.messages[0], messages[0])
  assert.deepEqual(result.messages.slice(-3), messages.slice(-3))
})
test('threshold equality triggers, threshold minus one does not', async () => {
  const meter = new TokenMeter(), messages = history(2, 5), fixed = meter.fixed('', [])
  const size = fixed + meter.messages(messages)
  // Exact threshold equality, with no safe range, still enters pressure path.
  const engine = make(invoke, { triggerRatio: .8, targetRatio: .5, retainTurns: 4 })
  const equal = await engine.project({ ...request(messages), instructions: '', budget: { contextWindow: Math.ceil(size / .8) + 10, outputReserve: 10, safetyMargin: 0 } })
  assert.equal(equal.status, 'no_safe_range')
  const below = await engine.project({ ...request(messages), instructions: '', budget: { contextWindow: Math.ceil((size + 1) / .8) + 10, outputReserve: 10, safetyMargin: 0 } })
  assert.equal(below.status, 'unchanged')
})
test('repeated SDK filter input uses validated request-local summary memo', async () => {
  let calls = 0
  const engine = make(async (...args) => { calls++; return invoke(...args) })
  const first = await engine.project(request()), count = calls
  const second = await engine.project(request())
  assert.ok(count >= 1); assert.equal(calls, count); assert.deepEqual(first.messages, second.messages)
  assert.equal(second.metrics.summaryCalls, 0)
})
test('different sessions and providers cannot reuse a checkpoint', async () => {
  let calls = 0
  const engine = make(async (...args) => { calls++; return invoke(...args) })
  await engine.project(request()); const first = calls
  const [a, b] = await Promise.all([engine.project({ ...request(), contextId: 'ctx-b' }), engine.project({ ...request(), provider: 'mock://two' })])
  assert.ok(calls > first); assert.equal(a.snapshot?.contextId, 'ctx-b'); assert.equal(b.snapshot?.provider, 'mock://two')
})
test('summary failure never changes input; in-budget pressure falls back explicitly', async () => {
  const input = request(history(3, 1100)), original = structuredClone(input)
  input.budget.contextWindow = 9000
  const engine = make(async () => { throw new Error('offline') })
  const result = await engine.project(input)
  assert.equal(result.status, 'failed_passthrough'); assert.equal(result.metrics.failed, true)
  assert.deepEqual(result.messages, original.messages); assert.deepEqual(input.messages, original.messages)
})
test('summary failure over the hard window blocks the request without dropping history', async () => {
  const input = request(), original = structuredClone(input)
  await assert.rejects(make(async () => { throw new Error('offline') }).project(input), /original history retained/)
  assert.deepEqual(input, original)
})
for (const bad of ['', '{}', JSON.stringify({ ...summary(), surprise: [] }), JSON.stringify(summary('x'.repeat(12000)))]) {
  test(`invalid summary rejects atomically ${bad.slice(0, 18)}`, async () => {
    const input = request(), original = structuredClone(input)
    await assert.rejects(make(async () => ({ text: bad })).project(input))
    assert.deepEqual(input, original)
  })
}
test('source mutation while awaiting summary is detected', async () => {
  const input = request()
  await assert.rejects(make(async (...args) => { input.messages[0].content = 'mutated'; return invoke(...args) }).project(input))
})
test('meter counts configured content exactly and degrades safely when encoding fails', () => {
  const meter = new TokenMeter(text => Array.from(text).length, 'fixture-codepoints')
  assert.equal(meter.text('中😀a'), 3)
  const broken = new TokenMeter(() => { throw new Error('unavailable') })
  assert.equal(broken.text('中😀a'), Buffer.byteLength('中😀a')); assert.equal(broken.fallbackUsed, true)
  assert.ok(broken.fixed('s', [{ name: 'tool' }]) > broken.fixed('s', []))
})
test('deterministic source references preserve Chinese file paths', () => {
  const refs = sourceReferences([{ role: 'user', content: '保留 docs/开发记录/上下文.md 与 src/工具.ts' }])
  assert.ok(refs.includes('docs/开发记录/上下文.md')); assert.ok(refs.includes('src/工具.ts'))
})
test('OpenAI tokenizer is model-specific; unknown DeepSeek model uses labelled bound', async () => {
  const gpt = await modelMeter('gpt-4o'), unknown = await modelMeter('deepseek-custom')
  assert.match(gpt.method, /tiktoken/); assert.equal(unknown.method, 'utf8-upper-bound')
  assert.ok(gpt.text('hello world') < Buffer.byteLength('hello world'))
})
test('unavailable configured tokenizer falls back explicitly without a network download', async () => {
  const meter = await modelMeter('deepseek-custom', { json: 'missing-tokenizer.json', config: 'missing-config.json' })
  assert.equal(meter.fallbackUsed, true)
  assert.equal(meter.text('中文😀'), Buffer.byteLength('中文😀'))
})
test('tool calls match IDs, not counts; duplicate/orphan results are rejected', () => {
  const call = { type: 'function_call', call_id: 'call-1', name: 'read_file', arguments: '{}' }
  assert.deepEqual(balancedCuts([call]), [true, false])
  assert.deepEqual(balancedCuts([call, { type: 'function_call_output', call_id: 'call-1', output: 'ok' }]), [true, false, true])
  assert.throws(() => balancedCuts([call, { type: 'function_call_output', call_id: 'other', output: 'bad' }]))
  assert.throws(() => balancedCuts([call, call]))
})
test('retention never splits parallel tool cycles or pending final tool calls', () => {
  const messages = [...history(3, 10), { type: 'function_call', call_id: 'a' }, { type: 'function_call', call_id: 'b' },
    { type: 'function_call_output', call_id: 'b', output: 'B' }, { type: 'function_call_output', call_id: 'a', output: 'A' }]
  const range = selectRange(messages, new TokenMeter(), 1, 1)!
  assert.ok(range[1] <= messages.length - 5)
  const cuts = balancedCuts(messages); assert.equal(cuts[range[1]], true)
  const pending = [...history(), { type: 'function_call', call_id: 'open' }]
  assert.deepEqual(pending.slice(selectRange(pending, new TokenMeter(), 1, 0)![1]).at(-1), { type: 'function_call', call_id: 'open' })
})
test('Unicode pruner preserves DSH head/tail and rich block order', () => {
  const config = { thresholdChars: 50, headChars: 4, tailChars: 3 }
  const result = pruneContent([{ type: 'text', text: '😀'.repeat(60) }], config)!
  assert.equal(result[0].text, '😀'.repeat(4) + PRUNE_MARKER + '😀'.repeat(3))
  const rich = { type: 'image', url: 'attachment:ref' }
  const blocks = pruneContent([{ type: 'text', text: 'A'.repeat(40) }, rich, { type: 'text', text: 'B'.repeat(40) }], config)!
  assert.deepEqual(blocks[1], rich); assert.equal(blocks.length, 3)
})
test('deterministic pruning preserves call IDs, structured errors and references', () => {
  const input = [{ type: 'function_call_output', call_id: 'call', output: JSON.stringify({ stdout: 'x'.repeat(14000), path: 'src/main.ts', errorCode: 'NONE' }) },
    { type: 'function_call_output', call_id: 'err', output: JSON.stringify({ status: 'failed', error: 'EACCESS', stderr: 'y'.repeat(14000) }) }]
  const result = pruneResults(input, DEFAULTS, 2)
  assert.equal(result.messages[0].call_id, 'call'); assert.equal(JSON.parse(result.messages[0].output).path, 'src/main.ts')
  assert.deepEqual(result.messages[1], input[1]); assert.ok(result.removedChars > 0)
})
test('tool-result pruning keeps opaque multimodal data blocks untouched', () => {
  const image = { type: 'image', content: 'binary-reference'.repeat(2000) }
  const output = [{ type: 'function_call_output', call_id: 'picture', output: [image, { type: 'text', text: 'x'.repeat(15000) }] }]
  const result = pruneResults(output, DEFAULTS, 1)
  assert.deepEqual(result.messages[0].output[0], image)
  assert.ok(result.removedChars > 0)
})
test('pruning alone can clear pressure without any summary call', async () => {
  const messages = [{ role: 'user', content: 'read' }, { type: 'function_call', call_id: 'c' },
    { type: 'function_call_output', call_id: 'c', output: 'x'.repeat(20000) }, { role: 'assistant', content: 'done' }, { role: 'user', content: 'now' }]
  const result = await make(async () => { throw new Error('must not summarize') }).project(request(messages))
  assert.equal(result.status, 'pruned'); assert.equal(result.messages[2].call_id, 'c'); balancedCuts(result.messages)
})
test('multimodal tail and its attachment reference stay byte-for-byte intact', async () => {
  const messages = history()
  messages[messages.length - 1] = { role: 'user', content: [{ type: 'input_text', text: 'look' }, { type: 'input_image', image_url: 'attachment:diagram' }] }
  const input = request(messages); input.budget.contextWindow = 30000
  const result = await make().project(input)
  assert.deepEqual(result.messages.at(-1), messages.at(-1))
})
test('a huge protected current user message cannot be silently shortened', async () => {
  const input = request([{ role: 'user', content: 'current'.repeat(10000) }])
  await assert.rejects(make().project(input), /original history retained/)
})
test('oversized source is mapped/reduced with bounded calls, no tools or recursive Runner', async () => {
  const meter = new TokenMeter(), seen: string[] = []
  const summarizer = new LLMSummarizer(async (text, _max, instruction) => {
    seen.push(text); assert.match(instruction, /Do not use tools/)
    assert.ok(meter.text(text) < 5000)
    return { text: JSON.stringify(summary('kept decision')), totalTokens: 50 }
  }, meter, { contextWindow: 5000, outputReserve: 600, safetyMargin: 200 }, 16)
  await summarizer.summarize(history(5, 1000), 600)
  assert.ok(seen.length > 1); assert.equal(summarizer.usageTokens, seen.length * 50)
})
test('budget reserves output, tools, system and safety; bad budgets/config fail', () => {
  assert.equal(inputLimit({ contextWindow: 10000, outputReserve: 1000, safetyMargin: 500 }), 8500)
  assert.throws(() => inputLimit({ contextWindow: 100, outputReserve: 100, safetyMargin: 0 }))
  assert.throws(() => make(invoke, { retainTurns: 0 }))
  assert.throws(() => make(invoke, { triggerRatio: .5, targetRatio: .7 }))
})
