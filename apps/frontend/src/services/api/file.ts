import axios from 'axios'
import { apiUrl, LOCAL_REQUEST_HEADERS } from '@/platform'

const api = axios.create({
  headers: LOCAL_REQUEST_HEADERS,
  baseURL: apiUrl('/api'),
  timeout: 240000
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





