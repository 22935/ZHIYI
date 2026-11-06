/** Reproducible five-scenario MOCK evaluation, never claimed as LLM quality. */
import { ContextCompactionEngine, TokenMeter, SUMMARY_FIELDS, wire } from '../src/index.ts'
import type { Message, ProjectionRequest } from '../src/index.ts'
export const scenarios = [
  { name: 'technical-dialogue', facts: ['KEY[decision=keep REST]', 'KEY[path=src/api.ts]', 'KEY[todo=add retry]'] },
  { name: 'code-audit', facts: ['KEY[decision=no global cache]', 'KEY[path=src/cache.ts]', 'KEY[todo=test race]'] },
  { name: 'tool-conversation', facts: ['KEY[result=exit 2]', 'KEY[path=src/cli.ts]', 'KEY[todo=fix EACCESS]'] },
  { name: 'document-analysis', facts: ['KEY[constraint=budget 1500]', 'KEY[path=docs/plan.md]', 'KEY[todo=verify quote]'] },
  { name: 'multi-stage-development', facts: ['KEY[decision=feature flag off]', 'KEY[path=src/runtime.ts]', 'KEY[todo=review migration]'] },
]
export async function evaluate() {
  const results = []
  for (const scenario of scenarios) {
    const messages: Message[] = [{ role: 'user', content: scenario.facts.join(' ') }]
    for (let i = 0; i < 8; i++) {
      messages.push({ role: 'assistant', content: 'audit evidence '.repeat(150) }, { role: 'user', content: 'continue analysis '.repeat(110) })
    }
    if (scenario.name === 'tool-conversation') messages.splice(3, 0,
      { type: 'function_call', call_id: 'tool-1', name: 'run_command', arguments: '{}' },
      { type: 'function_call_output', call_id: 'tool-1', output: JSON.stringify({ stdout: 'line\n'.repeat(3000), exitCode: 2, errorCode: 'EACCESS', path: 'src/cli.ts' }) })
    messages.push({ role: 'user', content: 'What were the decision, file path and unfinished work?' })
    const request: ProjectionRequest = { contextId: scenario.name, model: 'mock', provider: 'mock://evaluation', messages,
      instructions: 'Keep source facts; never guess.', tools: [], budget: { contextWindow: 16000, outputReserve: 1000, safetyMargin: 500 } }
    const engine = new ContextCompactionEngine(new TokenMeter(), async text => {
      const keys = text.match(/KEY\[[^\]]+\]/g) || []
      return { text: JSON.stringify(Object.fromEntries(SUMMARY_FIELDS.map(field => [field, field === 'facts' ? (keys.length ? [...new Set(keys)] : ['No additional confirmed facts in this fragment']) : []]))), totalTokens: 200 }
    }, { retainTurns: 1, retainRatio: 0 })
    const projected = await engine.project(request)
    const text = wire(projected.messages)
    const retained = scenario.facts.filter(fact => text.includes(fact)).length
    results.push({ scenario: scenario.name, ...projected.metrics, inputTokens: Number(projected.metrics.inputTokens), outputTokens: Number(projected.metrics.outputTokens), status: projected.status,
      expectedKeyFacts: scenario.facts.length, retainedKeyFacts: retained, keyFactRetention: retained / scenario.facts.length,
      qualitySource: 'mock-extraction-only', originalHistoryUnchanged: wire(messages) === wire(request.messages) })
  }
  return results
}
if (process.argv[1]?.endsWith('evaluate.ts')) console.log(JSON.stringify(await evaluate(), null, 2))
