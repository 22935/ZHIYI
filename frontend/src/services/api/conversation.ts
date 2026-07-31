import request from '@/utils/request'

export interface Conversation {
  id: string
  userId: string
  roleId?: string
  contextId: string
  title?: string
  preview?: string
  createdAt: string
  updatedAt: string
}

export interface ConversationDetail {
  conversation: Conversation
  preview: string
}

export const conversationApi = {
  // 获取用户的对话列表
  async getUserConversations(_userId?: string): Promise<Conversation[]> {
    const response = await request.get<Conversation[]>('/conversations')
    return response.data
  },

  // 获取对话详情
  async getConversation(contextId: string): Promise<Conversation> {
    const response = await request.get<Conversation>(`/conversations/${contextId}`)
    return response.data
  },

  // 获取对话详情（包含预览）
  async getConversationDetail(conversationId: string): Promise<ConversationDetail> {
    const response = await request.get<ConversationDetail>(`/conversations/${conversationId}/detail`)
    return response.data
  },

  // 删除对话
  async deleteConversation(conversationId: string): Promise<void> {
    await request.delete(`/conversations/${conversationId}`)
  },

  // 更新对话标题
  async updateTitle(conversationId: string, title: string): Promise<Conversation> {
    const response = await request.put<Conversation>(`/conversations/${conversationId}/title`, { title })
    return response.data
  },

  // 清空所有对话
  async deleteAllConversations(_userId?: string): Promise<void> {
    await request.delete('/conversations/all')
  }
}

