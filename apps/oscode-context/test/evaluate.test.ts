import { test } from 'node:test'
import assert from 'node:assert/strict'
import { evaluate } from './evaluate.ts'
test('five scenario mock evaluation retains decisions, paths and pending work', async () => {
  const results = await evaluate()
  assert.equal(results.length, 5)
  for (const result of results) {
    assert.equal(result.status, 'summarized')
    assert.equal(result.keyFactRetention, 1)
    assert.ok(Number(result.outputTokens) < Number(result.inputTokens))
  }
})
