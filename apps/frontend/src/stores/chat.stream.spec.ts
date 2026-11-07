import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStore } from './chat'
import type { ModelSettings } from '@/config/modelSettings'
import { chatApi } from '@/services/api/chat'
import { conversationApi } from '@/services/api/conversation'

const settings: ModelSettings = {
  provider: 'system', selectedModel: 'deepseek-flash', models: ['deepseek-flash'],
  apiKey: '', baseUrl: '', thinkingMode: 'standard'
}
const frame = (event: string, data: object) => `event:${event}\ndata:${JSON.stringify({event, data})}\n\n`
const respond = (chunks: string[], status = 200) => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk))
      controller.close()
    }
  }), {status})))
}
describe('Chat stream termination', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it.each(['ask', 'auto', 'full'] as const)('sends the selected %s approval mode with the tool request', async mode => {
    respond(['data:[DONE]'])
    const store = useChatStore()
    expect(store.approvalMode).toBe('ask')
    store.approvalMode = mode
    await store.sendMessageStream('检查文件', 'default', settings)
    const init = vi.mocked(fetch).mock.calls[0][1]!
    expect(JSON.parse(init.body as string)).toMatchObject({ tool_mode: 'auto', approval_mode: mode })
  })

  it('recognizes a split gateway error event and clears running status', async () => {
    respond([frame('reasoning_start', {}), 'event:err', 'or\r\ndata:{"code":"AI_UPSTREAM_TIMEOUT"}\r\n\r\n'])
    const store = useChatStore()
    await store.sendMessageStream('你好', 'default', settings)
    const reply = store.messages.at(-1)!
    expect(reply.content).toContain('模型响应超时')
    expect(reply.thinkingState).toBe('error')
    expect(reply.streamActivity).toBe('complete')
    expect(reply.streamPhase).toBe('请求未完成')
    expect(store.isStreaming).toBe(false)
    expect(reply.modelInfo).toBe('deepseek-flash')
  })

  it('preserves partial content while visibly marking an unexpected EOF', async () => {
    respond([frame('content_delta', {delta: '已收到的正文'})])
    const store = useChatStore()
    await store.sendMessageStream('介绍活动', 'default', settings)
    const reply = store.messages.at(-1)!
    expect(reply.content).toBe('已收到的正文')
    expect(reply.streamError).toContain('意外结束')
    expect(reply.thinkingState).toBe('error')
    expect(reply.streamActivity).toBe('complete')
  })

  it('does not turn a provider error followed by done into success', async () => {
    respond([frame('content_delta', {delta: '部分正文'}), frame('error', {code: 'AI_STREAM_FAILED'}), frame('done', {status:'completed'})])
    const store = useChatStore()
    await store.sendMessageStream('你好', 'default', settings)
    expect(store.messages.at(-1)?.thinkingState).toBe('error')
    expect(store.messages.at(-1)?.streamError).toContain('AI_STREAM_FAILED')
  })

  it('consumes the last frame without a newline and completes normally', async () => {
    respond([frame('content_delta', {delta:'你好'}), 'data:[DONE]'])
    const store = useChatStore()
    await store.sendMessageStream('你好', 'default', settings)
    expect(store.messages.at(-1)).toMatchObject({content:'你好', thinkingState:'complete',streamActivity:'complete'})
    expect(store.messages.at(-1)?.streamError).toBeUndefined()
  })

  it('finishes HTTP rejection without a running trace', async () => {
    respond([], 401)
    const store = useChatStore()
    await store.sendMessageStream('你好', 'default', settings)
    expect(store.messages.at(-1)).toMatchObject({thinkingState:'error',streamActivity:'complete',streamPhase:'请求未完成'})
  })

  it('stops a pending read without replacing partial text', async () => {
    let reading!: () => void
    const pendingRead = new Promise<void>(resolve => { reading = resolve })
    vi.stubGlobal('fetch', vi.fn().mockImplementation(async (_url, init) => {
      let first = true
      return {ok:true, headers:new Headers(), body:{getReader:() => ({read:() => {
        if (first) {
          first = false
          return Promise.resolve({done:false,value:new TextEncoder().encode(frame('content_delta', {delta:'部分正文'}))})
        }
        reading()
        return new Promise((_resolve,reject) => init.signal.addEventListener('abort', () => reject(new DOMException('Stopped','AbortError'))))
      }})}}
    }))
    const store = useChatStore()
    const running = store.sendMessageStream('介绍活动', 'default', settings)
    await pendingRead
    await store.cancelMessageStream()
    await running
    expect(store.messages.at(-1)).toMatchObject({content:'部分正文',streamError:'已停止生成',streamActivity:'complete'})
    expect(store.loading).toBe(false)
  })

  it('restores an interrupted reply from the existing history summary', async () => {
    vi.spyOn(conversationApi, 'getConversation').mockResolvedValue({ contextId: 'ctx-history' } as any)
    vi.spyOn(chatApi, 'getHistory').mockResolvedValue([{
      id:'reply',role:'ASSISTANT',content:'部分正文',metadata:{thinkingEnabled:true,
        executionSummary:[{stage:'chat_stream',status:'failed',description:'模型连接中断，请重试'}]}
    }])
    const store = useChatStore()
    await store.loadHistory('ctx-history')
    expect(store.messages.at(-1)).toMatchObject({content:'部分正文',thinkingState:'error',streamActivity:'complete',streamError:'模型连接中断，请重试'})
  })
})
