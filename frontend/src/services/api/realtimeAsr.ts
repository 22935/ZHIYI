/**
 * 实时语音识别服务
 * 支持WebSocket流式语音识别
 */

export interface RealtimeASROptions {
  language?: string
  sampleRate?: number
  onPartialResult?: (text: string, confidence: number) => void
  onFinalResult?: (text: string, confidence: number) => void
  onError?: (error: string) => void
}

export class RealtimeASRService {
  private ws: WebSocket | null = null
  private sessionId: string = ''
  private options: RealtimeASROptions = {}
  private isConnected: boolean = false

  /**
   * 开始实时识别会话
   */
  async startSession(options: RealtimeASROptions = {}): Promise<void> {
    this.options = options
    this.sessionId = `asr_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    
    // 构建WebSocket URL:
    // 1) 优先使用 VITE_API_BASE_URL 的主机信息（如果是绝对地址）
    // 2) 否则回退到当前页面主机（开发环境 5173 下可直接走 Vite 代理）
    const apiBase = (import.meta as any).env.VITE_API_BASE_URL as string | undefined
    let protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    let host = window.location.host

    if (apiBase && /^https?:\/\//.test(apiBase)) {
      const parsed = new URL(apiBase)
      protocol = parsed.protocol === 'https:' ? 'wss:' : 'ws:'
      host = parsed.host
    }

    const wsUrl = `${protocol}//${host}/ai/realtime-asr/${this.sessionId}`
    
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(wsUrl)
        
        this.ws.onopen = () => {
          this.isConnected = true
          // 发送开始消息
          this.ws?.send(JSON.stringify({
            type: 'start',
            language: options.language || 'zh-CN',
            sample_rate: options.sampleRate || 16000
          }))
          resolve()
        }
        
        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            this.handleMessage(data)
          } catch (e) {
            console.error('解析WebSocket消息失败:', e)
            options.onError?.('解析消息失败')
          }
        }
        
        this.ws.onerror = (error) => {
          console.error('WebSocket错误:', error)
          this.isConnected = false
          options.onError?.('WebSocket连接错误')
          reject(error)
        }
        
        this.ws.onclose = () => {
          this.isConnected = false
          console.log('WebSocket连接已关闭')
        }
      } catch (error) {
        console.error('创建WebSocket连接失败:', error)
        reject(error)
      }
    })
  }

  /**
   * 处理WebSocket消息
   */
  private handleMessage(data: any): void {
    switch (data.type) {
      case 'started':
        console.log('实时识别会话已开始:', data.session_id)
        break
        
      case 'partial':
        // 部分识别结果
        this.options.onPartialResult?.(data.text || '', data.confidence || 0.7)
        break
        
      case 'final':
        // 最终识别结果
        this.options.onFinalResult?.(data.text || '', data.confidence || 0.9)
        break
        
      case 'error':
        // 错误消息
        this.options.onError?.(data.message || '未知错误')
        break
        
      default:
        console.warn('未知的WebSocket消息类型:', data.type)
    }
  }

  /**
   * 发送音频数据
   */
  sendAudio(audioData: ArrayBuffer | Blob): void {
    if (!this.ws || !this.isConnected) {
      console.warn('WebSocket未连接，无法发送音频数据')
      return
    }
    
    try {
      // 如果audioData是Blob，先转换为ArrayBuffer
      if (audioData instanceof Blob) {
        audioData.arrayBuffer().then(buffer => {
          this.ws?.send(buffer)
        }).catch(error => {
          console.error('转换音频数据失败:', error)
          this.options.onError?.('发送音频数据失败')
        })
      } else {
        this.ws.send(audioData)
      }
    } catch (error) {
      console.error('发送音频数据失败:', error)
      this.options.onError?.('发送音频数据失败')
    }
  }

  /**
   * 结束识别会话
   */
  endSession(): void {
    if (this.ws && this.isConnected) {
      try {
        this.ws.send(JSON.stringify({ type: 'end' }))
      } catch (error) {
        console.error('发送结束消息失败:', error)
      }
    }
    this.close()
  }

  /**
   * 关闭WebSocket连接
   */
  close(): void {
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.isConnected = false
  }

  /**
   * 检查连接状态
   */
  get connected(): boolean {
    return this.isConnected && this.ws?.readyState === WebSocket.OPEN
  }
}

