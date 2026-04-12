import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatApi, type ChatRequest } from '@/services/api/chat'

export interface Message {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  fileUrl?: string
  createdAt?: Date
  timestamp?: number
  audioUrl?: string
  animation?: any
  confidence?: number
  tokensUsed?: number
  sources?: any[]
  reasoningPath?: any[]
  modelInfo?: string
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const loading = ref(false)
  const contextId = ref<string | null>(null)
  const currentRoleId = ref<string | null>(null)

  const sendMessage = async (text: string, fileUrl?: string) => {
    if ((!text.trim() && !fileUrl) || loading.value) return

    const userMessage: Message = {
      id: Date.now(),
      role: 'user',
      content: text || (fileUrl ? '[文件]' : ''),
      createdAt: new Date()
    }
    if (fileUrl) {
      (userMessage as any).fileUrl = fileUrl
    }
    messages.value.push(userMessage)

    loading.value = true
    try {
      const request: ChatRequest = {
        text: text || '',
        roleId: currentRoleId.value || undefined,
        contextId: contextId.value || undefined,
        fileUrl: fileUrl || undefined
      }

      const response = await chatApi.sendMessage(request)
      contextId.value = response.contextId

      const assistantMessage: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.text,
        createdAt: new Date(),
        confidence: response.confidence,
        tokensUsed: response.tokensUsed,
        sources: response.sources,
        reasoningPath: response.reasoningPath,
        modelInfo: response.modelInfo
      } as any
      messages.value.push(assistantMessage)

      return response
    } finally {
      loading.value = false
    }
  }

  const clearHistory = async () => {
    if (contextId.value) {
      await chatApi.clearHistory(contextId.value)
    }
    messages.value = []
    contextId.value = null
  }

  const setRole = (roleId: string | null) => {
    currentRoleId.value = roleId
  }

  // 加载对话历史
  const loadHistory = async (targetContextId: string) => {
    if (!targetContextId) return

    loading.value = true
    try {
      const history = await chatApi.getHistory(targetContextId)
      
      // 将后端消息格式转换为前端格式
      messages.value = history.map((msg: any) => ({
        id: msg.id || Date.now() + Math.random(),
        role: msg.role?.toLowerCase() === 'user' ? 'user' : 'assistant',
        content: msg.content || '',
        createdAt: msg.createdAt ? new Date(msg.createdAt) : new Date(),
        fileUrl: msg.fileUrl
      }))
      
      contextId.value = targetContextId
    } catch (error: any) {
      console.error('加载对话历史失败:', error)
      messages.value = []
    } finally {
      loading.value = false
    }
  }

  // 设置上下文ID（用于从外部设置，如从对话列表选择）
  const setContextId = (id: string | null) => {
    contextId.value = id
    if (id) {
      loadHistory(id)
    } else {
      messages.value = []
    }
  }

  // 添加消息（用于直接添加消息到列表）
  const addMessage = (message: Message) => {
    // 确保消息数据完整
    const completeMessage: Message = {
      ...message,
      id: message.id || Date.now().toString(),
      role: message.role || 'user',
      content: message.content || '',
      createdAt: message.createdAt || (message.timestamp ? new Date(message.timestamp) : new Date()),
      timestamp: message.timestamp || (message.createdAt ? message.createdAt.getTime() : Date.now())
    }
    messages.value.push(completeMessage)
  }

  // 设置消息列表（用于批量设置消息）
  const setMessages = (newMessages: Message[]) => {
    messages.value = newMessages.map(msg => ({
      ...msg,
      createdAt: msg.createdAt || (msg.timestamp ? new Date(msg.timestamp) : new Date())
    }))
  }

  // 清除消息（用于清除当前对话）
  const clearMessages = () => {
    messages.value = []
    contextId.value = null
  }

  return {
    messages,
    loading,
    contextId,
    currentRoleId,
    sendMessage,
    clearHistory,
    setRole,
    loadHistory,
    setContextId,
    addMessage,
    setMessages,
    clearMessages
  }
})

