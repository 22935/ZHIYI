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

export interface RoleInfo {
  roleId: string
  knowledgeDomain: string[]
  personality?: string
}

export interface RoleFusionRequest {
  question: string
  availableRoles: RoleInfo[]
  roleResponses: Record<string, string>
}

export const roleFusionApi = {
  /**
   * 融合多个角色的回答
   */
  async fuseRoles(request: RoleFusionRequest): Promise<Record<string, any>> {
    const response = await api.post<{ success: boolean; data: Record<string, any> }>(
      '/role-fusion/fuse',
      request
    )
    return response.data.data || {}
  },

  /**
   * 计算角色权重
   */
  async calculateRoleWeights(
    question: string,
    availableRoles: RoleInfo[]
  ): Promise<Record<string, any>> {
    const response = await api.post<{ success: boolean; data: Record<string, any> }>(
      '/role-fusion/weights',
      availableRoles,
      {
        params: {
          question
        }
      }
    )
    return response.data.data || {}
  }
}

