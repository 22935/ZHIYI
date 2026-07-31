import request from '@/utils/request'
import type { ThinkingMode } from '@/config/modelSettings'

export interface ChatRequest {
  text?: string
  message?: string
  roleId?: string
  contextId?: string
  fileUrl?: string
  emotionTag?: string
  context?: Array<{ role: string; content: string }>
  model?: string
  baseUrl?: string
  apiKey?: string
  thinkingMode?: ThinkingMode
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

export const chatApi = {
  // 发送文本消息
  async sendMessage(chatRequest: ChatRequest): Promise<ChatResponse & { audioUrl?: string; animation?: any }> {
    const response = await request.post<ChatResponse & { audioUrl?: string; animation?: any }>('/chat/text', {
      text: chatRequest.text || chatRequest.message,
      roleId: chatRequest.roleId,
      contextId: chatRequest.contextId,
      fileUrl: chatRequest.fileUrl,
      context: chatRequest.context,
      model: chatRequest.model,
      baseUrl: chatRequest.baseUrl,
      apiKey: chatRequest.apiKey,
      thinkingMode: chatRequest.thinkingMode,
      tool_mode: chatRequest.toolMode || 'auto'
    })
    return response.data
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

