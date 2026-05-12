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

export interface FileUploadResponse {
  filePath: string
  originalFilename: string
  size: number
  contentType: string
  error?: string
}

export interface FileInfo {
  id: string
  name: string
  path: string
  size: number
  type: string
  uploadTime: string
}

export const fileApi = {
  // 上传文件
  async uploadFile(file: File, type: string = 'general'): Promise<FileUploadResponse> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('type', type)
    
    const response = await api.post<FileUploadResponse>('/files/upload', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
    return response.data
  },

  // 下载文件
  async downloadFile(type: string, filename: string): Promise<Blob> {
    const response = await api.get(`/files/download/${type}/${filename}`, {
      responseType: 'blob'
    })
    return response.data
  },

  // 删除文件
  async deleteFile(type: string, filename: string): Promise<void> {
    await api.delete(`/files/${type}/${filename}`)
  },

  // 获取文件列表（如果后端支持）
  async getFileList(type?: string): Promise<FileInfo[]> {
    const params = type ? { type } : {}
    const response = await api.get<FileInfo[]>('/files', { params })
    return response.data
  }
}





