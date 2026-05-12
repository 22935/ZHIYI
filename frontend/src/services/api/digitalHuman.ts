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

// 响应拦截器：处理错误
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    // 如果响应中有数据，返回数据；否则返回错误信息
    if (error.response && error.response.data) {
      return Promise.reject(error.response.data)
    }
    return Promise.reject(error)
  }
)

export interface DigitalHumanRequest {
  roleId: string
  personality?: string
  profession?: string
  style?: string
  name?: string  // 形象名称
  description?: string  // 形象描述
  avatarId?: string  // 形象ID（可选，不提供则自动生成）
}

export interface DigitalHumanResponse {
  success: boolean
  data?: any
  message?: string
}

export const digitalHumanApi = {
  /**
   * 创建数字人
   */
  async createDigitalHuman(request: DigitalHumanRequest): Promise<DigitalHumanResponse> {
    const response = await api.post<DigitalHumanResponse>('/digital-human/create', request)
    return response.data
  },

  /**
   * 更新数字人动画
   */
  async updateAnimation(
    roleId: string,
    text: string,
    audioFile: File
  ): Promise<DigitalHumanResponse> {
    const formData = new FormData()
    formData.append('roleId', roleId)
    formData.append('text', text)
    formData.append('audio', audioFile)

    const response = await api.post<DigitalHumanResponse>(
      '/digital-human/animation',
      formData,
      {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      }
    )
    return response.data
  },

  /**
   * 切换数字人风格
   */
  async switchStyle(roleId: string, newStyle: string): Promise<DigitalHumanResponse> {
    const response = await api.post<DigitalHumanResponse>('/digital-human/style', null, {
      params: {
        roleId,
        newStyle
      }
    })
    return response.data
  },

  /**
   * 获取数字人信息（用于加载已创建的数字人）
   */
  async getDigitalHuman(roleId: string, avatarId?: string): Promise<DigitalHumanResponse> {
    try {
      const params = avatarId ? { avatar_id: avatarId } : {}
      const response = await api.get<DigitalHumanResponse>(`/digital-human/${roleId}`, { params })
      return response.data
    } catch (error: any) {
      // 检查是否是 404 错误
      const status = error.response?.status || error.status
      const is404 = status === 404 || 
                    (error.message && error.message.includes('404')) ||
                    (error.detail && error.detail.includes('不存在')) ||
                    (error.success === false && (error.message?.includes('不存在') || error.detail?.includes('不存在')))
      
      if (is404) {
        // 如果是 404 错误，返回一个明确的错误响应，而不是抛出异常
        // 这是正常情况，数字人不存在时会返回 404
        return {
          success: false,
          message: `数字人不存在: ${roleId}`
        }
      }
      // 其他错误继续抛出
      throw error
    }
  },

  /**
   * 列出角色的所有数字人形象
   */
  async listRoleAvatars(roleId: string): Promise<DigitalHumanResponse> {
    const response = await api.get<DigitalHumanResponse>(`/digital-human/${roleId}/avatars`)
    return response.data
  },

  /**
   * 删除数字人形象
   */
  async deleteAvatar(avatarId: string): Promise<DigitalHumanResponse> {
    const response = await api.delete<DigitalHumanResponse>(`/digital-human/avatar/${avatarId}`)
    return response.data
  },

  /**
   * 更新形象显示设置
   */
  async updateAvatarSettings(avatarId: string, settings: any): Promise<DigitalHumanResponse> {
    const response = await api.put<DigitalHumanResponse>(`/digital-human/avatar/${avatarId}/settings`, {
      avatar_id: avatarId,
      settings
    })
    return response.data
  }
}

