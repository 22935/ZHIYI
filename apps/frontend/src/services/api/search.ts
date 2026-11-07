import axios from 'axios'
import type { Message } from '@/stores/chat'
import { apiUrl, LOCAL_REQUEST_HEADERS } from '@/platform'

const api = axios.create({
  headers: LOCAL_REQUEST_HEADERS,
  baseURL: apiUrl('/api'),
  timeout: 240000
})

export const searchApi = {
  // 搜索对话消息
  async searchMessages(keyword: string, contextId?: string): Promise<Message[]> {
    const params: any = { keyword }
    if (contextId) {
      params.contextId = contextId
    }
    const response = await api.get<Message[]>('/search/messages', { params })
    return response.data
  },

  // 搜索所有消息
  async searchAllMessages(keyword: string): Promise<Message[]> {
    const response = await api.get<Message[]>('/search/all-messages', {
      params: { keyword }
    })
    return response.data
  }
}

