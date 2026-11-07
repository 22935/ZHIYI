import { localFetch } from '@/platform/api'
import { agentosRequest } from '../client'
import { runPath } from '../paths'
import { apiUrl } from '@/platform'

export interface CopilotStreamEvent { type: 'content' | 'activity' | 'heartbeat' | 'completed' | 'error'; content?: string; message?: string; exchange?: CopilotExchange }
export interface CopilotMessageOptions { modelId?: string; permission: CopilotPermission; reasoningEffort?: string }

export interface CopilotExchange {
  sourceRunId?: string
  operationId: string; user: string; assistant: string; createdAt: string; observedRevision: number
  modelId?: string | null; permission?: CopilotPermission
  reasoningEffort?: string | null
  action?: CopilotAction
  receipt?: { proposalId: string; runId: string; kind: CopilotActionKind; status: string; executeStepIds: string[]; reusedStepIds: string[] }
}
export type CopilotActionKind = 'rerun' | 'rerun_node' | 'recover' | 'user_input'
export interface CopilotAction { kind: CopilotActionKind; stepId: string | null; expectedRevision: number; executeStepIds: string[]; reusedStepIds: string[]; content: string; capabilityCatalogRevision?: string; executionEnvironmentChanged?: boolean }
export type CopilotPermission = 'read_only' | 'task_collaboration'
export interface CopilotState {
  missionId?: string; latestRunId?: string; taskPermission?: CopilotPermission
  runId: string; status: string; revision: number; modelAvailable: boolean
  models?: { id: string; provider: string; model: string; reasoningEfforts?: string[]; defaultReasoningEffort?: string | null }[]
  defaultModelId?: string | null; permissions?: CopilotPermission[]
  question: { questionId: string; prompt: string; choices: string[] } | null
  humanAnswers: { questionId: string; sourceRunId: string; prompt: string; answer: string; answeredAt: string }[]
  exchanges: CopilotExchange[]
  decision: { action: string; reason: string } | null
  review?: { subjectId: string; subjectType: string; reason: string; reasonCode: string; canApprove: boolean; decisionRejected: boolean; expectedRunUpdatedAt: string } | null
  steps: { stepId: string; name: string; status: string }[]
}
export const createCopilotApi = () => ({
  async setCopilotPermission(runId: string, permission: CopilotPermission): Promise<{ missionId: string; taskPermission: CopilotPermission }> {
    return (await agentosRequest.post(`${runPath(runId)}/copilot/permission`, { permission })).data
  },
  async previewCopilotAction(runId: string, kind: CopilotActionKind, content: string, operationId: string, permission: CopilotPermission, stepId?: string): Promise<CopilotExchange> {
    return (await agentosRequest.post(`${runPath(runId)}/copilot/actions/preview`, { kind, content, operationId, permission, ...(stepId ? { stepId } : {}) })).data
  },
  async applyCopilotAction(runId: string, proposalId: string, expectedRevision: number, permission: CopilotPermission): Promise<CopilotExchange> {
    return (await agentosRequest.post(`${runPath(runId)}/copilot/actions`, { proposalId, expectedRevision, permission })).data
  },
  async getCopilot(runId: string, signal?: AbortSignal): Promise<CopilotState> {
    return (await agentosRequest.get(`${runPath(runId)}/copilot`, { signal })).data
  },
  async streamCopilotMessage(runId: string, content: string, operationId: string, onEvent: (event: CopilotStreamEvent) => void, signal?: AbortSignal, options?: CopilotMessageOptions): Promise<CopilotExchange> {

    const response = await localFetch(apiUrl(`/api/agentos/v2${runPath(runId)}/copilot/messages/stream`), {
      method: 'POST', signal, headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ content, operationId, ...options })
    })
    if (!response.ok) {
      const error = Object.assign(new Error(`对话连接失败（${response.status}）`), { response: { status: response.status } })
      throw error
    }
    if (!response.body) throw new Error('服务未返回流式响应')
    const reader = response.body.getReader(), decoder = new TextDecoder()
    let buffer = '', completed: CopilotExchange | undefined
    function consume(block: string) {
      const data = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
      if (!data) return
      const event = JSON.parse(data) as CopilotStreamEvent & { event?: string }
      if (event.type === 'error' || event.event === 'error') throw new Error(event.message || '对话流中断，请重试')
      onEvent(event)
      if (event.type === 'completed') completed = event.exchange
    }
    try {
      while (!completed) {
        const { done, value } = await reader.read()
        buffer += decoder.decode(value, { stream: !done }).replace(/\r/g, '')
        let boundary: number
        while ((boundary = buffer.indexOf('\n\n')) >= 0) { consume(buffer.slice(0, boundary)); buffer = buffer.slice(boundary + 2) }
        if (done) { if (buffer.trim()) consume(buffer); break }
      }
      if (!completed) throw new Error('对话流提前结束，回复尚未保存，请重试')
      return completed
    } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
  },
  async sendCopilotMessage(runId: string, content: string, operationId: string, signal?: AbortSignal, options?: CopilotMessageOptions): Promise<CopilotExchange> {
    return (await agentosRequest.post(`${runPath(runId)}/copilot/messages`, { content, operationId, ...options }, { signal })).data
  },
  async answerPlanner(runId: string, questionId: string, answer: string, expectedRevision: number, operationId: string, permission?: CopilotPermission): Promise<CopilotState> {
    return (await agentosRequest.post(`${runPath(runId)}/copilot/answers`, { questionId, answer, expectedRevision, operationId, ...(permission ? { permission } : {}) })).data
  }
})
