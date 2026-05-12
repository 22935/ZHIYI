import request from '@/utils/request'
import type { AxiosError } from 'axios'

export interface Role {
  id: string
  name: string
  description: string
  roleType: 'BUILTIN' | 'CUSTOM'
  systemPrompt?: string
  dialogueStyle?: any
  personality?: any
  avatarConfig?: any
  avatar?: string
}

export interface RoleCreateRequest {
  name: string
  description?: string
  systemPrompt: string
  dialogueStyle?: any
  personality?: any
  avatarConfig?: any
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

const isRateLimitError = (error: unknown) => {
  const status = (error as AxiosError)?.response?.status
  return status === 429
}

export const roleApi = {
  async getBuiltinRoles(): Promise<Role[]> {
    const response = await request.get<Role[]>('/roles/builtin')
    return Array.isArray(response.data) ? response.data : []
  },

  async getCustomRoles(): Promise<Role[]> {
    try {
      const response = await request.get<Role[]>('/roles/custom')
      return Array.isArray(response.data) ? response.data : []
    } catch (error) {
      if (!isRateLimitError(error)) throw error

      // Back off once for transient 429s, then fallback to last known empty list.
      await sleep(700)
      try {
        const retryResponse = await request.get<Role[]>('/roles/custom')
        return Array.isArray(retryResponse.data) ? retryResponse.data : []
      } catch (retryError) {
        if (!isRateLimitError(retryError)) throw retryError
        return []
      }
    }
  },

  async getRole(roleId: string): Promise<Role> {
    const response = await request.get<Role>(`/roles/${roleId}`)
    return response.data
  },

  async createRole(roleRequest: RoleCreateRequest): Promise<Role> {
    const response = await request.post<Role>('/roles/custom', roleRequest)
    return response.data
  },

  async updateRole(roleId: string, roleRequest: RoleCreateRequest): Promise<Role> {
    const response = await request.put<Role>(`/roles/${roleId}`, roleRequest)
    return response.data
  },

  async deleteRole(roleId: string): Promise<void> {
    await request.delete(`/roles/${roleId}`)
  },
}
