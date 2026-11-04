import { conversationBindings, isActiveRunStatus, runMatchesSelection } from './session'
import type { ChatWorkflowBinding } from '@/stores/chat'
import type { Conversation } from '@/services/api/conversation'
import type { VerifiedSessionRun } from './session'
import type { InjectionKey } from 'vue'

export const conversationBindingKey: InjectionKey<(conversationId: string, missionId: string, runId: string | null) => boolean> = Symbol('conversation-binding')

type Index = Record<string, ChatWorkflowBinding[]>
type ReadRun = (id: string) => Promise<VerifiedSessionRun>

export async function conversationWorkbenchTarget(index: Index, conversationId: string, selectedRunId: string | undefined, readRun: ReadRun) {
  const bindings = conversationBindings(index, conversationId).filter(item => !item.invalidAt)
  const binding = selectedRunId ? bindings.find(item => item.runId === selectedRunId)
    : [...bindings].reverse().find(item => isActiveRunStatus(item.status)) || bindings[bindings.length - 1]
  if (!binding) return null
  const owners = () => new Set(Object.values(index).flat().filter(item => !item.invalidAt
    && item.runId === binding.runId)
    .map(item => `${item.conversationId}\u0000${item.missionId}`))
  if (owners().size !== 1) return null
  try {
    const run = await readRun(binding.runId)
    if (!runMatchesSelection(run, binding.runId, binding.missionId)) return null
    if (owners().size !== 1 || !conversationBindings(index, conversationId).some(item =>
      !item.invalidAt && item.runId === binding.runId && item.missionId === binding.missionId)) return null
    return { path: `/agentos/missions/${encodeURIComponent(run.missionId)}/workspace`, query: { runId: run.runId } }
  } catch { return null }
}

export async function workbenchConversationTarget(options: {
  index: Index; missionId: string; runId: string; draftId: string | null; currentContextId: string | null
  readRun: ReadRun; readConversation: (id: string) => Promise<Conversation>
}) {
  const { missionId, runId } = options
  const bindings = Object.values(options.index).flat().filter(item =>
    !item.invalidAt && item.missionId === missionId && item.runId === runId)
  // An alias belongs to its canonical binding; competing canonical conversations
  // for the same Run are ambiguous and never resolved by insertion order.
  const ids = new Set(bindings.map(item => item.conversationId))
  if (ids.size !== 1) return null
  const binding = bindings[0]
  try {
    const run = await options.readRun(runId)
    if (!runMatchesSelection(run, runId, missionId)) return null
    if (binding.conversationId.startsWith('draft:')) {
      if (binding.conversationId !== options.draftId || options.currentContextId) return null
      return { path: '/chat', query: { workspace: binding.source, missionId, runId } }
    }
    const conversation = await options.readConversation(binding.conversationId)
    if (conversation.contextId !== binding.conversationId) return null
    return { path: '/chat', query: {
      contextId: conversation.contextId, missionId, runId,
      workspace: conversation.workspaceMode || binding.source
    } }
  } catch { return null }
}

export const isConversationForWorkbench = (index: Index, conversationId: string, missionId: string, runId: string | null) =>
  Boolean(runId && conversationBindings(index, conversationId).some(item =>
    !item.invalidAt && item.missionId === missionId && item.runId === runId))
