import axios from 'axios'

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

export interface EmotionAnalyzeRequest {
  text?: string
  audioFeatures?: Record<string, any>
  facialFeatures?: Record<string, any>
}

export interface EmotionAwareResponseRequest {
  question: string
  baseRole: Record<string, any>
  text?: string
  audioFeatures?: Record<string, any>
  facialFeatures?: Record<string, any>
  userEmotion?: Record<string, any>
}

export const emotionApi = {
  /**
   * 多模态情感分析
   */
  async analyzeEmotion(request: EmotionAnalyzeRequest): Promise<Record<string, any>> {
    const response = await api.post<{ success: boolean; data: Record<string, any> }>(
      '/emotion/analyze',
      request
    )
    return response.data.data || {}
  },

  /**
   * 生成情感感知回复
   */
  async generateEmotionAwareResponse(
    request: EmotionAwareResponseRequest
  ): Promise<Record<string, any>> {
    const response = await api.post<{ success: boolean; data: Record<string, any> }>(
      '/emotion/response',
      request
    )
    return response.data.data || {}
  }
}

