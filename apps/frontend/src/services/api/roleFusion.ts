import axios from 'axios'
import { apiUrl, LOCAL_REQUEST_HEADERS } from '@/platform'

const api = axios.create({
  headers: LOCAL_REQUEST_HEADERS,
  baseURL: apiUrl('/api'),
  timeout: 240000
})

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

