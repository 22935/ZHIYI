import { apiUrl } from '@/platform/api'
import { parseChatStreamFrame } from '@/utils/sse'
import type { ChatPort, CompanionContext } from '../types'

const CONTEXT_STORAGE_KEY = 'companion.chat_context_id.v1'

/**
 * 可选的真实模型对话适配器：复用既有 SSE 帧协议，但使用独立的 context_id，
 * 不写入 chatStore、不改动 /ai/chat/text/stream 的行为。
 *
 * 注意：这是 P0 的过渡通道。P1 接入 /ai/companion/* 专用端点后，
 * 只需替换 ChatPort 的实现，UI 与业务层无需变化。
 */
export class StreamChatPort implements ChatPort {
  private contextId: string | null = null

  private resolveContextId(): string {
    if (this.contextId) return this.contextId
    let stored: string | null = null
    try {
      stored = localStorage.getItem(CONTEXT_STORAGE_KEY)
    } catch {
      stored = null
    }
    const id = stored || `companion:${Date.now().toString(36)}:${Math.random().toString(36).slice(2, 8)}`
    this.contextId = id
    try {
      localStorage.setItem(CONTEXT_STORAGE_KEY, id)
    } catch {
      // Storage can be unavailable in embedded webviews; keep the in-memory id.
    }
    return id
  }

  async reply(text: string, _context: CompanionContext, signal?: AbortSignal): Promise<string> {
    const token = localStorage.getItem('token')
    if (!token) return '需要先登录，我才能调用模型陪你聊天。'
    const response = await fetch(apiUrl('/ai/chat/text/stream'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`
      },
      body: JSON.stringify({
        text,
        tool_mode: 'auto',
        context_id: this.resolveContextId(),
        workspace_mode: 'chat'
      }),
      signal
    })
    if (!response.ok || !response.body) throw new Error(`Companion stream failed with HTTP ${response.status}`)

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let content = ''
    let failure = ''
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      const frames = buffer.replace(/\r\n/g, '\n').split('\n\n')
      buffer = done ? '' : frames.pop() || ''
      for (const frame of frames) {
        const event = parseChatStreamFrame(frame)
        if (!event) continue
        if (event.event === 'content_delta') content += String(event.data.delta ?? '')
        if (event.event === 'error') failure = String(event.data.code ?? 'AI_STREAM_FAILED')
        if (event.event === 'done' || failure) break
      }
      if (done || failure) break
    }
    if (failure) throw new Error(failure)
    return content.trim() || '模型没有返回内容，换个说法再问我一次吧。'
  }
}
