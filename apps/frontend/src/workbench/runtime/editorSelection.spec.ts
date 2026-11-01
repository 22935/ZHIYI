import { expect, it } from 'vitest'
import { initialEditorIntent, selectLifecycleEditor } from './editorSelection'
import type { LifecycleProjection } from './lifecycleProjection'
const life = (phase: string, entry: string | null = null) => ({ runId: 'a', phase, recommendedEntryId: entry } as LifecycleProjection)
it('hands off once per transition and waits for the final identity to arrive', () => {
  let intent = initialEditorIntent()
  for (const phase of ['PLANNING', 'RUNNING', 'WAITING_REVIEW', 'FAILED', 'COMPLETED']) {
    const first = selectLifecycleEditor(intent, life(phase)); expect(first.handoff).toBe(true); intent = first.intent
    expect(selectLifecycleEditor(intent, life(phase)).handoff).toBe(false)
  }
  const late = selectLifecycleEditor(intent, life('COMPLETED', 'final'))
  expect(late.handoff).toBe(true); expect(selectLifecycleEditor(late.intent, life('COMPLETED', 'final')).handoff).toBe(false)
})
it('never steals a manually selected file; explicit Follow resumes once', () => {
  const intent = { ...selectLifecycleEditor(initialEditorIntent(), life('RUNNING')).intent, mode: 'user' as const }
  expect(selectLifecycleEditor(intent, life('COMPLETED', 'final')).handoff).toBe(false)
  expect(selectLifecycleEditor({ ...intent, mode: 'follow', handled: null }, life('COMPLETED', 'final')).handoff).toBe(true)
})
it('keeps intent over KeepAlive refresh and starts a new policy for a different Run', () => {
  const selected = { ...selectLifecycleEditor(initialEditorIntent(), life('RUNNING')).intent, mode: 'user' as const }
  expect(selectLifecycleEditor(selected, life('RUNNING')).handoff).toBe(false)
  expect(selectLifecycleEditor(selected, { ...life('PLANNING'), runId: 'b' }).handoff).toBe(true)
})
