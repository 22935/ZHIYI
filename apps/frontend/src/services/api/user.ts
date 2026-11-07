import request from '@/utils/request'

export interface User {
  id?: string
  username?: string
  email?: string
  avatar?: string
  createdAt?: Date | string
}

export interface UpdateUserRequest {
  username?: string
  email?: string
}

export interface AvatarUploadResponse extends User {
  avatar?: string
}

export const userApi = {
  // 获取当前用户信息
  async getCurrentUser(): Promise<User> {
    const response = await request.get<User>('/user/profile')
    return response.data
  },

  // 获取用户信息
  async getUser(userId: string): Promise<User> {
    const response = await request.get<User>(`/users/${userId}`)
    return response.data
  },

  // 更新用户信息
  async updateUser(userId: string, userData: UpdateUserRequest): Promise<User> {
    const response = await request.put<User>(`/users/${userId}`, userData)
    return response.data
  },

  async uploadAvatar(userId: string, file: File): Promise<AvatarUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)
    const response = await request.post<AvatarUploadResponse>(`/users/${userId}/avatar`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  },

  async getAvatar(userId: string): Promise<Blob> {
    const response = await request.get<Blob>(`/users/${userId}/avatar`, {
      responseType: 'blob'
    })
    return response.data
  }
}
