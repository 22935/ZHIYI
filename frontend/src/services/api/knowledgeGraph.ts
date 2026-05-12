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

export interface DocumentInfo {
  docId: string
  text: string
  metadata?: Record<string, any>
}

export interface BuildKnowledgeGraphRequest {
  documents: DocumentInfo[]
}

export const knowledgeGraphApi = {
  /**
   * 从文档构建知识图谱
   */
  async buildKnowledgeGraph(
    request: BuildKnowledgeGraphRequest
  ): Promise<Record<string, any>> {
    const response = await api.post<{ success: boolean; data: Record<string, any> }>(
      '/knowledge-graph/build',
      request
    )
    return response.data.data || {}
  },

  /**
   * 混合检索：知识图谱 + 向量数据库
   */
  async hybridSearch(
    question: string,
    vectorDbResults: Record<string, any>[],
    topK: number = 5
  ): Promise<Record<string, any>> {
    const response = await api.post<{ success: boolean; data: Record<string, any> }>(
      '/knowledge-graph/search',
      vectorDbResults,
      {
        params: {
          question,
          topK
        }
      }
    )
    return response.data.data || {}
  },

  /**
   * 基于知识图谱进行推理
   */
  async reasonWithKnowledgeGraph(question: string): Promise<Record<string, any>> {
    const response = await api.post<{ success: boolean; data: Record<string, any> }>(
      '/knowledge-graph/reason',
      null,
      {
        params: {
          question
        }
      }
    )
    return response.data.data || {}
  },

  /**
   * 获取知识图谱统计信息
   */
  async getGraphStats(): Promise<Record<string, any>> {
    const response = await api.get<{ success: boolean; data: Record<string, any> }>(
      '/knowledge-graph/stats'
    )
    return response.data.data || {}
  },

  /**
   * 查询实体相关信息
   */
  async getEntityInfo(
    entityId: string,
    relation?: string,
    limit: number = 10
  ): Promise<Record<string, any>> {
    const response = await api.get<{ success: boolean; data: Record<string, any> }>(
      `/knowledge-graph/entity/${entityId}`,
      {
        params: {
          relation,
          limit
        }
      }
    )
    return response.data.data || {}
  },

  /**
   * 获取完整的知识图谱数据（用于可视化）
   */
  async getGraphData(roleId?: string): Promise<{
    nodes: Array<{ id: string; label: string; type: string; properties: any }>
    edges: Array<{ from: string; to: string; label: string; arrows: string }>
    stats: { entities_count: number; triples_count: number; relations_count: number }
  }> {
    const params = roleId ? { role_id: roleId } : {}
    const response = await api.get<{
      success: boolean
      data: {
        nodes: Array<{ id: string; label: string; type: string; properties: any }>
        edges: Array<{ from: string; to: string; label: string; arrows: string }>
        stats: { entities_count: number; triples_count: number; relations_count: number }
      }
    }>('/knowledge-graph/graph-data', { params })
    return response.data.data
  }
}

