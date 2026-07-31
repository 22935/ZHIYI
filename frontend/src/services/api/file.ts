import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 240000
})

const materialApi = axios.create({
  baseURL: '/ai',
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

materialApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

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

export interface DocumentExtractionResult {
  success: boolean
  text: string
  filename?: string
  file_type?: string
  type?: string
  metadata?: Record<string, unknown>
  content?: string
  note?: string
}

export interface TaskMaterial {
  materialId: string
  state: 'ready' | 'bound'
  originalFilename: string
  mediaType: string
  size: number
  sha256: string
  extractedTextSha256: string
  extractedText: string
  textLength: number
  extraction: {
    method: string
    ocrUsed: boolean
    pages: number
  }
}

export const fileApi = {
  async uploadTaskMaterial(file: File, onUploaded?: () => void): Promise<TaskMaterial> {
    const formData = new FormData()
    formData.append('file', file)
    // Do not set Content-Type here: the browser must add the multipart boundary.
    let uploadCompleted = false
    const response = await materialApi.post<TaskMaterial>('/core/materials', formData, {
      onUploadProgress: progress => {
        if (!uploadCompleted && progress.total && progress.loaded >= progress.total) {
          uploadCompleted = true
          onUploaded?.()
        }
      }
    })
    return response.data
  },

  async deleteTaskMaterial(materialId: string): Promise<void> {
    await materialApi.delete(`/core/materials/${encodeURIComponent(materialId)}`)
  },

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

  // 上传文档到 AI 文档处理服务并提取正文
  async extractDocumentText(file: File): Promise<DocumentExtractionResult> {
    const formData = new FormData()
    formData.append('file', file)

    const response = await api.post<{
      success: boolean
      data?: DocumentExtractionResult
      detail?: string
    }>('/ai/multimodal/document', formData, {
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })

    const result = response.data?.data
    if (!response.data?.success || !result?.success) {
      throw new Error(result?.content || result?.note || response.data?.detail || '文档解析失败')
    }
    return result
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





