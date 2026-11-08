import axios, { AxiosError, AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import { apiUrl, LOCAL_REQUEST_HEADERS } from '@/platform'
import {
  markErrorAsUserNotified
} from './requestErrors'

export { wasErrorUserNotified } from './requestErrors'

const request = axios.create({
  baseURL: apiUrl('/api'),
  timeout: 240000,
  headers: {
    ...LOCAL_REQUEST_HEADERS,
    'Content-Type': 'application/json'
  }
})

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
    let userNotified = false
    const notifyError = (message: string) => {
      ElMessage.error(message)
      userNotified = true
    }

    if (error.response) {
      const status = error.response.status
      const payload = error.response.data as any
      const message = payload?.message ?? payload?.detail?.message
      const backendMessage = typeof message === 'string' ? message : undefined

      switch (status) {
        case 400:
          notifyError(backendMessage || '请求参数错误')
          break
        case 401:
          notifyError(backendMessage || '本机服务认证失败，请检查运行配置')
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
          notifyError(backendMessage || '服务暂时不可用，请稍后重试')
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

