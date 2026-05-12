import axios from 'axios'
import type { Message } from '@/stores/chat'

const api = axios.create({
  baseURL: '/api',
  timeout: 240000
})

// 请求拦截器：添加Token
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

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

