import type { CopilotPermission, CopilotState } from '@/services/api/agentos/api/copilot'

// Presentation cache only. Fresh server state is required before submitting.
interface Session { state: CopilotState; draft: string; model: string; permission: CopilotPermission; effort: string; operation?: { content: string; target: string; id: string; options: string } }
const sessions = new Map<string, Session>()
let account: string | null | undefined
function checkAccount() {
  const next = localStorage.getItem('userId')
  if (account !== next) { sessions.clear(); account = next }
}
export function getCopilotSession(runId: string) {
  checkAccount()
  const value = sessions.get(runId)
  return value ? JSON.parse(JSON.stringify(value)) as Session : undefined
}
export function saveCopilotSession(runId: string, session: Session, ownerId: string | null) {
  checkAccount()
  if (ownerId !== account) return
  sessions.delete(runId)
  sessions.set(runId, JSON.parse(JSON.stringify(session)))
  while (sessions.size > 8) sessions.delete(sessions.keys().next().value!)
}
export function clearCopilotSession(runId: string) { sessions.delete(runId) }
