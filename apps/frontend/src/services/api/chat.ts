import request from '@/utils/request'
import type { ReasoningEffort, ThinkingMode } from '@/config/modelSettings'
import type { ContextMessage } from '@/features/chat/compaction'

export interface CompactResponse {
  contextId: string
  status: 'unchanged' | 'pruned' | 'summarized' | 'no_safe_range' | 'failed_passthrough'
  messages: ContextMessage[]
  model: string
  contextWindowTokens: number
  metrics: Record<string, string | number | boolean>
}

export interface ChatRequest {
  text?: string
  message?: string
  roleId?: string
  contextId?: string
  workspaceMode?: 'agent' | 'chat'
  fileUrl?: string
  emotionTag?: string
  context?: Array<{ role: string; content: string }>
  model?: string
  baseUrl?: string
  apiKey?: string
  thinkingMode?: ThinkingMode
  reasoningEffort?: ReasoningEffort
  toolMode?: 'auto' | 'disabled'
}

export interface Source {
  title?: string
  filename?: string
  url?: string
  content?: string
  snippet?: string
  provider?: string
  citationId?: string
  retrievedAt?: string
}

export interface ReasoningStep {
  title: string
  description: string
}

export interface ChatResponse {
  text: string
  contextId: string
  confidence: number
  tokensUsed?: number
  animation?: any
  sources?: Source[]
  reasoningPath?: ReasoningStep[]
  modelInfo?: string
  metadata?: Record<string, any>
}

export type ChatApprovalDecision = 'allow_once' | 'allow_session' | 'deny'

export const chatApi = {
  async compactContext(payload: {
    context_id: string; context: ContextMessage[]; role_id?: string
    model?: string; base_url?: string; api_key?: string
  }, signal?: AbortSignal): Promise<CompactResponse> {
    const response = await request.post<CompactResponse>('/ai/chat/compact', payload, { signal, timeout: 130000 })
    return response.data
  },
  // 发送文本消息
  async sendMessage(chatRequest: ChatRequest): Promise<ChatResponse & { audioUrl?: string; animation?: any }> {
    const response = await request.post<ChatResponse & { audioUrl?: string; animation?: any }>('/chat/text', {
      text: chatRequest.text || chatRequest.message,
      roleId: chatRequest.roleId,
      contextId: chatRequest.contextId,
      workspaceMode: chatRequest.workspaceMode,
      fileUrl: chatRequest.fileUrl,
      context: chatRequest.context,
      model: chatRequest.model,
      baseUrl: chatRequest.baseUrl,
      apiKey: chatRequest.apiKey,
      thinkingMode: chatRequest.thinkingMode,
      reasoningEffort: chatRequest.reasoningEffort,
      tool_mode: chatRequest.toolMode || 'auto'
    })
    return response.data
  },

  async resolveApproval(
    approvalId: string,
    payload: {
      decision: ChatApprovalDecision
      sessionId: string
      invocationId?: string
      capabilityId?: string
      relativePath?: string
    }
  ) {
    const response = await request.post(`/ai/chat/approvals/${encodeURIComponent(approvalId)}`, payload)
    return response.data as { approvalId: string; status: string; decision: ChatApprovalDecision }
  },

  async cancelExecution(requestId: string) {
    const response = await request.post('/ai/chat/text/cancel', { requestId })
    return response.data as { requestId: string; cancelled: boolean }
  },

  // 获取对话历史
  async getHistory(contextId: string) {
    const response = await request.get(`/chat/history/${contextId}`)
    return response.data
  },

  // 获取角色对话历史
  async getConversationHistory(roleId: string) {
    try {
      const response = await request.get(`/chat/history/role/${roleId}`)
      return response.data
    } catch (error) {
      // 如果API不存在，返回空数据
      return {
        messages: [],
        summary: ''
      }
    }
  },

  // 获取对话摘要
  async getConversationSummary(roleId: string) {
    try {
      const response = await request.get(`/chat/summary/${roleId}`)
      return response.data.summary || ''
    } catch (error) {
      // 如果API不存在，返回空字符串
      return ''
    }
  },

  // 清除对话历史
  async clearHistory(contextId: string) {
    await request.delete(`/chat/history/${contextId}`)
  }
}

