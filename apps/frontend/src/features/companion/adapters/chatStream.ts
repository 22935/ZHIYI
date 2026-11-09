import { apiUrl, localFetch } from '@/platform/api'
import { parseChatStreamFrame } from '@/utils/sse'
import type { ChatPort, CompanionContext } from '../types'

const CONTEXT_STORAGE_KEY = 'companion.chat_context_id.v1'
/**
 * 伙伴默认走模型回复，但只在轻量档位上跑：
 * - thinking 关闭：闲聊不需要推理链，直接砍掉首字延迟；
 * - 不指定模型：沿用服务端激活供应商的默认档（现网为 *-flash / 轻量档）；
 * - 允许本地钉死：在 localStorage 写入该键可强制使用某个更小的模型，
 *   留空则完全交给服务端默认。
 */
const MODEL_OVERRIDE_KEY = 'companion.chat_model.v1'

const readModelOverride = (): string | null => {
  try { return localStorage.getItem(MODEL_OVERRIDE_KEY)?.trim() || null } catch { return null }
}

/**
 * 虚拟伙伴复用平台聊天协议，并保留服务端创建的独立 Conversation。
 * 首条消息省略 context_id，后续消息只复用服务端返回的上下文。
 */
export class StreamChatPort implements ChatPort {
  private contextId: string | null = null

  private resolveContextId(): string | null {
    if (this.contextId) return this.contextId
    let stored: string | null = null
    try {
      stored = localStorage.getItem(CONTEXT_STORAGE_KEY)
    } catch {
      stored = null
    }
    // Older adapters invented these IDs without creating a Conversation.
    // They cannot be submitted as owner-checked references to the new backend.
    if (stored?.startsWith('companion:')) {
      try { localStorage.removeItem(CONTEXT_STORAGE_KEY) } catch { /* optional storage */ }
      stored = null
    }
    this.contextId = stored?.trim() || null
    return this.contextId
  }

  private rememberContextId(value: unknown): void {
    if (typeof value !== 'string' || !value.trim()) return
    this.contextId = value.trim()
    try {
      localStorage.setItem(CONTEXT_STORAGE_KEY, this.contextId)
    } catch {
      // Storage can be unavailable in embedded webviews; keep the in-memory id.
    }
  }

  async reply(text: string, _context: CompanionContext, signal?: AbortSignal): Promise<string> {

    const contextId = this.resolveContextId()
    const model = readModelOverride()
    const response = await localFetch(apiUrl('/ai/chat/text/stream'), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text,
        tool_mode: 'auto',
        // 伙伴闲聊不需要深度思考；轻量档是它「回复快」的前提。
        thinking_mode: 'disabled',
        ...(model ? { model } : {}),
        ...(contextId ? { context_id: contextId } : {}),
        workspace_mode: 'chat'
      }),
      signal
    })
    if (!response.ok || !response.body) throw new Error(`Companion stream failed with HTTP ${response.status}`)
    this.rememberContextId(response.headers.get('X-Context-Id') || response.headers.get('X-Chat-Context-Id'))

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
        if (/^event:\s*meta\s*$/m.test(frame)) {
          const data = frame.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n')
          try {
            const meta = JSON.parse(data)
            this.rememberContextId(meta.contextId ?? meta.meta?.contextId ?? meta.data?.contextId)
          } catch { /* A malformed metadata frame does not discard the model reply. */ }
        }
        const event = parseChatStreamFrame(frame)
        if (!event) continue
        this.rememberContextId(event.data.contextId ?? event.data.meta?.contextId)
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
