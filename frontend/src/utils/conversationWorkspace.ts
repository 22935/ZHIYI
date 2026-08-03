export type ConversationWorkspaceMode = 'agent' | 'chat'

const STORAGE_KEY = 'chat.conversation_workspace.v1'

const readWorkspaceIndex = (): Record<string, ConversationWorkspaceMode> => {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}')
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}

    return Object.fromEntries(
      Object.entries(parsed).filter((entry): entry is [string, ConversationWorkspaceMode] =>
        entry[1] === 'agent' || entry[1] === 'chat'
      )
    )
  } catch {
    return {}
  }
}

export const getConversationWorkspace = (
  contextId: string,
  agentConversationIds: ReadonlySet<string> = new Set()
): ConversationWorkspaceMode => {
  const normalizedId = contextId.trim()
  if (!normalizedId) return 'chat'

  const storedMode = readWorkspaceIndex()[normalizedId]
  if (storedMode) return storedMode

  // Older Agent sessions predate the workspace index but can still be
  // identified by their persisted Workflow binding.
  return agentConversationIds.has(normalizedId) ? 'agent' : 'chat'
}

export const setConversationWorkspace = (
  contextId: string,
  mode: ConversationWorkspaceMode
) => {
  const normalizedId = contextId.trim()
  if (!normalizedId || normalizedId.startsWith('draft:')) return

  const workspaceIndex = readWorkspaceIndex()
  if (workspaceIndex[normalizedId] === mode) return
  workspaceIndex[normalizedId] = mode
  localStorage.setItem(STORAGE_KEY, JSON.stringify(workspaceIndex))
  window.dispatchEvent(new Event('conversation-workspace-change'))
}

export const removeConversationWorkspace = (contextId: string) => {
  const normalizedId = contextId.trim()
  const workspaceIndex = readWorkspaceIndex()
  if (!normalizedId || !workspaceIndex[normalizedId]) return

  delete workspaceIndex[normalizedId]
  localStorage.setItem(STORAGE_KEY, JSON.stringify(workspaceIndex))
  window.dispatchEvent(new Event('conversation-workspace-change'))
}

export const clearConversationWorkspaces = () => {
  localStorage.removeItem(STORAGE_KEY)
  window.dispatchEvent(new Event('conversation-workspace-change'))
}
