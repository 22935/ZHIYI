import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { StreamChatPort } from './chatStream'
import type { CompanionContext } from '../types'

const context: CompanionContext = { messages: [], progress: null, personaName: '知宝' }
const storageKey = 'companion.chat_context_id.v1'
const frame = (event: string, data: object) => `event: ${event}\ndata: ${JSON.stringify({ event, data })}\n\n`
const response = (stream: string, headers: Record<string, string> = {}) => {
  const bytes = new TextEncoder().encode(stream)
  return new Response(new ReadableStream({ start(controller) {
    for (let index = 0; index < bytes.length; index += 3) controller.enqueue(bytes.slice(index, index + 3))
    controller.close()
  } }), { headers: { 'Content-Type': 'text/event-stream', ...headers } })
}

describe('Companion server conversation continuity', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('omits the first context and persists the split SSE metadata context for later adapters', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response('event: meta\ndata: {"contextId":"ctx_server-owned"}\n\n'
        + frame('content_delta', { delta: '你好😀' }) + frame('done', { status: 'completed' })))
      .mockResolvedValueOnce(response(frame('content_delta', { delta: '记得你' }) + frame('done', { status: 'completed' })))
    vi.stubGlobal('fetch', fetcher)

    expect(await new StreamChatPort().reply('你好', context)).toBe('你好😀')
    const body = JSON.parse(fetcher.mock.calls[0][1].body)
    // 模型回复是默认档，但走轻量档位：不指定模型、思考关闭。
    expect(body.thinking_mode).toBe('disabled')
    expect(body).not.toHaveProperty('model')
    expect(body).not.toHaveProperty('context_id')
    expect(localStorage.getItem(storageKey)).toBe('ctx_server-owned')
    expect(await new StreamChatPort().reply('还记得吗', context)).toBe('记得你')
    expect(JSON.parse(fetcher.mock.calls[1][1].body).context_id).toBe('ctx_server-owned')
    expect(new Headers(fetcher.mock.calls[0][1].headers).get('X-Zhiyi-Local-Request')).toBe('1')
  })

  it('pins a smaller model when the user overrides it locally', async () => {
    localStorage.setItem('companion.chat_model.v1', ' deepseek-flash ')
    const fetcher = vi.fn().mockResolvedValue(response(frame('content_delta', { delta: '在' }) + frame('done', {})))
    vi.stubGlobal('fetch', fetcher)
    await new StreamChatPort().reply('你好', context)
    expect(JSON.parse(fetcher.mock.calls[0][1].body).model).toBe('deepseek-flash')
  })

  it('discards legacy invented companion ids instead of sending an unknown conversation', async () => {
    localStorage.setItem(storageKey, 'companion:old:random')
    const fetcher = vi.fn().mockResolvedValue(response(frame('done', { contextId: 'ctx_created' })))
    vi.stubGlobal('fetch', fetcher)
    await new StreamChatPort().reply('重新开始', context)
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).not.toHaveProperty('context_id')
    expect(localStorage.getItem(storageKey)).toBe('ctx_created')
  })

  it('reuses the backend response header context within the same adapter', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(response(frame('done', {}), { 'X-Context-Id': 'ctx_header' }))
      .mockResolvedValueOnce(response(frame('done', {})))
    vi.stubGlobal('fetch', fetcher)
    const port = new StreamChatPort()
    await port.reply('第一条', context)
    await port.reply('第二条', context)
    expect(JSON.parse(fetcher.mock.calls[1][1].body).context_id).toBe('ctx_header')
  })

  it('does not persist a context from rejected requests or retry a different owner reference', async () => {
    localStorage.setItem(storageKey, 'ctx_existing')
    const fetcher = vi.fn().mockResolvedValue(new Response('', { status: 404 }))
    vi.stubGlobal('fetch', fetcher)
    await expect(new StreamChatPort().reply('你好', context)).rejects.toThrow('404')
    expect(fetcher).toHaveBeenCalledOnce()
    expect(localStorage.getItem(storageKey)).toBe('ctx_existing')
  })

  it('preserves caller cancellation and upstream stream errors', async () => {
    const controller = new AbortController()
    const fetcher = vi.fn().mockResolvedValue(response(frame('error', { code: 'AI_UPSTREAM_TIMEOUT' })))
    vi.stubGlobal('fetch', fetcher)
    await expect(new StreamChatPort().reply('你好', context, controller.signal)).rejects.toThrow('AI_UPSTREAM_TIMEOUT')
    expect(fetcher.mock.calls[0][1].signal).toBe(controller.signal)
  })
})
