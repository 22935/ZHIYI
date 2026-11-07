import { afterEach, describe, expect, it, vi } from 'vitest'
import { createCopilotApi } from './copilot'

vi.mock('@/platform', () => ({ apiUrl: (path: string) => path, LOCAL_REQUEST_HEADERS: { 'X-Zhiyi-Local-Request': '1' } }))
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); vi.clearAllMocks() })

function response(frames: unknown[]) {
  const bytes = new TextEncoder().encode(frames.map(frame => `data: ${JSON.stringify(frame)}\r\n\r\n`).join(''))
  return new Response(new ReadableStream({ start(controller) {
    for (let index = 0; index < bytes.length; index += 3) controller.enqueue(bytes.slice(index, index + 3))
    controller.close()
  } }), { headers: { 'Content-Type': 'text/event-stream' } })
}

describe('Copilot SSE transport', () => {
  it('decodes split UTF-8 frames and forwards local model/effort options', async () => {
    const exchange = { operationId: 'op', assistant: '你好\n😀', user: 'hello', createdAt: '', observedRevision: 0 }
    const fetcher = vi.fn().mockResolvedValue(response([{ type: 'content', content: '你好' }, { type: 'completed', exchange }]))
    vi.stubGlobal('fetch', fetcher); localStorage.setItem('token', 'test-token')
    const event = vi.fn()
    const result = await createCopilotApi().streamCopilotMessage('run/id', 'hello', 'op', event, undefined, { permission: 'read_only', modelId: 'test/model', reasoningEffort: 'high' })
    expect(result).toEqual(exchange)
    expect(event.mock.calls[0][0]).toEqual({ type: 'content', content: '你好' })
    expect(fetcher.mock.calls[0][0]).toContain('/runs/run%2Fid/copilot/messages/stream')
    const options = fetcher.mock.calls[0][1]
    expect(new Headers(options.headers).get('Authorization')).toBeNull()
    expect(new Headers(options.headers).get('X-Zhiyi-Local-Request')).toBe('1')
    expect(JSON.parse(options.body).reasoningEffort).toBe('high')
  })
  it('rejects truncated or failed streams instead of treating previews as completed', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(response([{ type: 'content', content: 'partial' }])).mockResolvedValueOnce(response([{ type: 'error', message: 'provider failed' }])))
    const api = createCopilotApi()
    await expect(api.streamCopilotMessage('run', 'hello', 'op', vi.fn())).rejects.toThrow('提前结束')
    await expect(api.streamCopilotMessage('run', 'hello', 'op', vi.fn())).rejects.toThrow('provider failed')
  })
  it('reports service authentication failure without losing local identity', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })))
    await expect(createCopilotApi().streamCopilotMessage('run', 'hello', 'op', vi.fn())).rejects.toThrow('401')
    expect(localStorage.getItem('token')).toBeNull()
  })
})
