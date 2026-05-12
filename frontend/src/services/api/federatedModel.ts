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

// 响应拦截器：处理错误
api.interceptors.response.use(
  (response) => {
    return response
  },
  (error) => {
    if (error.response && error.response.data) {
      return Promise.reject(error.response.data)
    }
    return Promise.reject(error)
  }
)

export interface ModelInfo {
  name: string
  type: string
  status: string
  optimized: boolean
  version: string
  performance?: {
    accuracy: number
    speed: number
    efficiency: number
  }
}

export interface ModelEvaluationResult {
  model_type: string
  task_type: string
  evaluation_time: string
  metrics: {
    accuracy: number
    response_time: number
    success_rate: number
    throughput: number
    resource_usage: number
    cost_per_request: number
  }
  comparison: {
    baseline_accuracy: number
    improvement: number
    improvement_percentage: number
  }
  recommendations: string[]
}

export interface ModelOptimizationResult {
  model_type: string
  optimization_method: string
  status: string
  optimization_time: string
  improvements: {
    accuracy?: number
    efficiency?: number
    speed?: number
  }
  new_version: string
  optimized_params?: any
}

export const federatedModelApi = {
  /**
   * 获取所有联邦学习模型列表
   */
  async listModels(): Promise<{ success: boolean; data: Record<string, Record<string, ModelInfo>> }> {
    try {
      const response = await api.get('/ai/federated-models/list')
      return response.data
    } catch (error: any) {
      // 如果 Python 服务不可用，返回空数据而不是抛出错误
      console.warn('联邦模型列表获取失败，Python服务可能未启动:', error)
      return {
        success: false,
        data: {}
      }
    }
  },

  /**
   * 获取优化状态
   */
  async getOptimizationStatus(): Promise<{ success: boolean; data: any }> {
    const response = await api.get('/ai/federated-models/status')
    return response.data
  },

  /**
   * 评估模型性能
   */
  async evaluateModel(modelType: string, taskType?: string, testSamples?: number): Promise<{ success: boolean; data: ModelEvaluationResult }> {
    const response = await api.post('/ai/federated-models/evaluate', {
      model_type: modelType,
      task_type: taskType,
      test_samples: testSamples
    })
    return response.data
  },

  /**
   * 优化模型
   */
  async optimizeModel(
    modelType: string,
    optimizationMethod: string = 'federated',
    targetMetric: string = 'quality',
    epochs?: number
  ): Promise<{ success: boolean; data: ModelOptimizationResult }> {
    const response = await api.post('/ai/federated-models/optimize', {
      model_type: modelType,
      optimization_method: optimizationMethod,
      target_metric: targetMetric,
      epochs
    })
    return response.data
  },

  /**
   * 批量评估模型
   */
  async batchEvaluateModels(modelTypes: string[], taskType?: string): Promise<{ success: boolean; data: any }> {
    const response = await api.post('/ai/federated-models/batch-evaluate', {
      model_types: modelTypes,
      task_type: taskType
    })
    return response.data
  },

  /**
   * 获取模型详细信息
   */
  async getModelDetails(modelType: string): Promise<{ success: boolean; data: any }> {
    const response = await api.get(`/ai/federated-models/${modelType}/details`)
    return response.data
  }
}

