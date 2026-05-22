import request from '@/utils/request'

export interface LoginRequest {
  username: string
  password: string
  email?: string
}

export interface LoginResponse {
  token?: string
  userId?: string | number
  username?: string
  message?: string
  success?: boolean
}

export const authApi = {
  // 登录
  async login(loginRequest: LoginRequest): Promise<LoginResponse & { success?: boolean }> {
    const response = await request.post<LoginResponse & { success?: boolean }>('/auth/login', loginRequest)
    return response.data
  },

  // 注册
  async register(registerRequest: LoginRequest): Promise<LoginResponse & { success?: boolean }> {
    const response = await request.post<LoginResponse & { success?: boolean }>('/auth/register', registerRequest)
    return response.data
  },

  // 验证Token
  async verifyToken(): Promise<{ valid: boolean; userId?: string; username?: string }> {
    const token = localStorage.getItem('token')
    if (!token) {
      return { valid: false }
    }

    try {
      const response = await request.get<{ valid: boolean; userId?: string; username?: string }>('/auth/verify')
      return response.data
    } catch {
      return { valid: false }
    }
  },

  // 退出登录
  async logout(): Promise<{ success: boolean; message?: string }> {
    try {
      // 清除本地存储的token
      localStorage.removeItem('token')
      localStorage.removeItem('userId')
      localStorage.removeItem('userInfo')
      
      // 可以调用后端接口进行token失效（如果有的话）
      // 目前后端没有logout接口，所以只在前端清除
      
      return { success: true, message: '退出登录成功' }
    } catch (error: any) {
      console.error('退出登录失败:', error)
      return { success: false, message: error.message || '退出登录失败' }
    }
  }
}

