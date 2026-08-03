import axios, { AxiosError, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'

const USER_NOTIFIED_FLAG = '__kinlinUserNotified'

type UserNotifiedError = Error & { [USER_NOTIFIED_FLAG]?: boolean }

const markErrorAsUserNotified = <T extends Error>(error: T): T => {
  (error as UserNotifiedError)[USER_NOTIFIED_FLAG] = true
  return error
}

export const wasErrorUserNotified = (error: unknown): boolean =>
  error instanceof Error && Boolean((error as UserNotifiedError)[USER_NOTIFIED_FLAG])

// 创建axios实例
const request = axios.create({
  baseURL: '/api',
  timeout: 240000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
request.interceptors.request.use(
  (config) => {
    const requestUrl = config.url || ''
    const isPublicAuthOperation =
      requestUrl.includes('/auth/login') ||
      requestUrl.includes('/auth/register')

    // 公开认证接口不能携带本地残留的旧令牌，否则 JWT 过滤器会在登录前拒绝请求。
    const token = localStorage.getItem('token')
    if (token && !isPublicAuthOperation) {
      config.headers.Authorization = `Bearer ${token}`
    } else if (isPublicAuthOperation) {
      delete config.headers.Authorization
    }
    return config
  },
  (error) => {
    return Promise.reject(error)
  }
)

// 响应拦截器
request.interceptors.response.use(
  (response: AxiosResponse) => {
    // 统一处理响应数据格式
    if (response.data && typeof response.data === 'object') {
      // 如果后端返回的是 { success: true, data: ... } 格式，提取data
      if ('success' in response.data && 'data' in response.data) {
        return { ...response, data: response.data.data }
      }
      // 如果后端返回的是 { success: false, message: ... } 格式，抛出错误
      if ('success' in response.data && !response.data.success) {
        const message = response.data.message || '请求失败'
        ElMessage.error(message)
        return Promise.reject(markErrorAsUserNotified(new Error(message)))
      }
    }
    return response
  },
  (error: AxiosError) => {
    const requestUrl = error.config?.url || ''
    const isAuthOperation =
      requestUrl.includes('/auth/login') ||
      requestUrl.includes('/auth/register') ||
      requestUrl.includes('/auth/verify')

    let userNotified = false
    const notifyError = (message: string) => {
      ElMessage.error(message)
      userNotified = true
    }

    if (error.response) {
      const status = error.response.status
      const backendMessage = (error.response.data as any)?.message as string | undefined

      switch (status) {
        case 400:
          notifyError(backendMessage || '请求参数错误')
          break
        case 401:
          // 登录、注册、验签接口自身返回401时，不做全局重定向，交由页面处理。
          if (!isAuthOperation) {
            notifyError('登录状态已过期，请重新登录')
            localStorage.removeItem('token')
            localStorage.removeItem('userId')

            // 避免循环重定向
            if (window.location.pathname !== '/login') {
              const redirect = encodeURIComponent(window.location.pathname + window.location.search)
              window.location.href = `/login?redirect=${redirect}`
            }
          }
          break
        case 403:
          notifyError(backendMessage || '拒绝访问')
          break
        case 404:
          notifyError(backendMessage || '请求资源不存在')
          break
        case 500:
          notifyError(backendMessage || '服务器内部错误')
          break
        case 502:
        case 503:
        case 504:
          notifyError('服务暂时不可用，请稍后重试')
          break
        default:
          notifyError(backendMessage || `请求失败: ${status}`)
      }
    } else if (error.request) {
      notifyError('网络错误，请检查网络连接')
    } else {
      notifyError('请求配置错误')
    }
    if (userNotified) markErrorAsUserNotified(error)
    return Promise.reject(error)
  }
)

export default request

