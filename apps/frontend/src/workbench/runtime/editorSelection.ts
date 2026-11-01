import type { LifecycleProjection } from './lifecycleProjection'

export interface EditorSelectionIntent { mode: 'follow' | 'user'; runId: string | null; handled: string | null }
export const initialEditorIntent = (): EditorSelectionIntent => ({ mode: 'follow', runId: null, handled: null })
export function selectLifecycleEditor(intent: EditorSelectionIntent, lifecycle: LifecycleProjection) {
  const key = JSON.stringify([lifecycle.runId, lifecycle.phase, lifecycle.recommendedEntryId, lifecycle.deliverable?.contentRef])
  const next = intent.runId !== lifecycle.runId ? { mode: 'follow' as const, runId: lifecycle.runId, handled: null } : intent
  if (next.mode === 'user' || next.handled === key) return { intent: next, handoff: false }
  return { intent: { ...next, handled: key }, handoff: true }
}
