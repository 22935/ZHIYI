import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatStore } from './chat'
import { chatApi, type CompactResponse } from '@/services/api/chat'
import type { ModelSettings } from '@/config/modelSettings'
import { MODEL_SETTINGS_EVENT } from '@/config/modelSettings'
import { estimateContextInput } from '@/features/chat/compaction'

const settings: ModelSettings = {
  provider: 'system', selectedModel: 'deepseek-flash', models: [], apiKey: '', baseUrl: '', thinkingMode: 'disabled'
}
const result: CompactResponse = { contextId: 'ctx-a', status: 'summarized', model: 'deepseek-flash',
  contextWindowTokens: 1_000_000, messages: [{ role: 'user', content: 'checkpoint: preserve REST' }],
  contextFixedTokens: 100, contextTokenMethod: 'utf8-upper-bound',
  metrics: { inputTokens: 12000, outputTokens: 400 } }
const ready = () => {
  const store = useChatStore()
  store.contextId = 'ctx-a'; store.conversationWorkspaceMode = 'chat'
  store.messages = [{ id: '1', role: 'user', content: 'preserve REST' },
    { id: '2', role: 'assistant', content: 'agreed' }]
  return store
}
const respond = () => vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response(
  'event:content_delta\ndata:{"event":"content_delta","data":{"delta":"next answer"}}\n\n'
  + 'event:done\ndata:{"event":"done","data":{"status":"completed","contextId":"ctx-a"}}\n\n')))

describe('manual OScode context compaction', () => {
  beforeEach(() => { localStorage.clear(); setActivePinia(createPinia()) })
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

  it('preserves raw records and sends checkpoint plus later turns on subsequent HTTP requests', async () => {
    const compact = vi.spyOn(chatApi, 'compactContext').mockResolvedValue(result)
    respond()
    const store = ready(), original = JSON.stringify(store.messages)
    await store.compactContext(settings)
    expect(JSON.stringify(store.messages)).toBe(original)
    expect(compact.mock.calls[0][0]).toMatchObject({ context_id: 'ctx-a', context: [
      { role: 'user', content: 'preserve REST' }, { role: 'assistant', content: 'agreed' }] })
    expect(store.compactionNotice).toContain('12,000 → 400')
    await store.sendMessageStream('next request', 'default', settings)
    const first = JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string)
    expect(first.context).toEqual(result.messages)
    expect(first.text).toBe('next request')
    await store.sendMessageStream('third request', 'default', settings)
    const next = JSON.parse(vi.mocked(fetch).mock.calls[1][1]!.body as string)
    expect(next.context).toEqual([...result.messages, { role: 'user', content: 'next request' },
      { role: 'assistant', content: 'next answer' }])
  })

  it('invalidates checkpoint if the original history was edited', async () => {
    vi.spyOn(chatApi, 'compactContext').mockResolvedValue(result); respond()
    const store = ready(); await store.compactContext(settings)
    store.messages[0].content = 'switch to GraphQL'
    await store.sendMessageStream('continue', 'default', settings)
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string).context).toBeUndefined()
  })

  it('ignores late compaction when another conversation owns the composer', async () => {
    let resolve!: (value: CompactResponse) => void
    vi.spyOn(chatApi, 'compactContext').mockImplementation(() => new Promise(ok => { resolve = ok }))
    const store = ready(), pending = store.compactContext(settings)
    expect(store.isCompacting).toBe(true)
    store.clearMessages(); store.contextId = 'ctx-b'
    store.messages = [{ id: 'b', role: 'user', content: 'other conversation' }]
    resolve(result); await pending
    expect(store.contextId).toBe('ctx-b'); expect(store.compactionNotice).toBe('')
    expect(store.contextUsedTokens).toBeNull(); expect(store.isCompacting).toBe(false)
  })

  it('keeps the current context after a failed compaction and does not send a command as a message', async () => {
    vi.spyOn(chatApi, 'compactContext').mockResolvedValue({ ...result, status: 'failed_passthrough' }); respond()
    const store = ready(), original = JSON.stringify(store.messages)
    await store.compactContext(settings)
    expect(store.compactionNotice).toContain('未通过压缩校验')
    expect(JSON.stringify(store.messages)).toBe(original)
    await store.sendMessageStream('continue', 'default', settings)
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string).context).toBeUndefined()
  })

  it('does not reuse a model-specific checkpoint after the selected model changes', async () => {
    vi.spyOn(chatApi, 'compactContext').mockResolvedValue(result); respond()
    const store = ready(); await store.compactContext(settings)
    await store.sendMessageStream('continue', 'default', { ...settings, selectedModel: 'other' })
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string).context).toBeUndefined()
    expect(store.nextContextTokens).toBeNull()
  })

  it('estimates the projected next input while retaining separate Provider usage', async () => {
    vi.spyOn(chatApi, 'compactContext').mockResolvedValue(result)
    const store = ready()
    store.contextUsedTokens = 93146
    await store.compactContext(settings)
    expect(store.contextUsedTokens).toBe(93146)
    expect(store.nextContextTokens).toBe(estimateContextInput(result.messages, 100))
    const sse = [
      { event: 'content_delta', data: { delta: 'next answer' } },
      { event: 'usage', data: { input_tokens: 90000, output_tokens: 1000,
        contextFixedTokens: 100, contextTokenMethod: 'utf8-upper-bound' } },
      { event: 'done', data: { status: 'completed', contextId: 'ctx-a' } }
    ].map(value => `data:${JSON.stringify(value)}\n\n`).join('')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(sse)))
    await store.sendMessageStream('next request', 'default', settings)
    expect(store.contextUsedTokens).toBe(91000)
    expect(store.nextContextTokens).toBe(estimateContextInput([...result.messages,
      { role: 'user', content: 'next request' }, { role: 'assistant', content: 'next answer' }], 100))
    expect(store.nextContextTokens).toBeLessThan(1000)
    // A service started before the metadata change still supplies Provider
    // usage only; the validated manual allowance remains usable.
    vi.mocked(fetch).mockResolvedValue(new Response(sse.replace(
      ',"contextFixedTokens":100,"contextTokenMethod":"utf8-upper-bound"', '')))
    await store.sendMessageStream('third request', 'default', settings)
    expect(store.nextContextTokens).toBe(estimateContextInput([...result.messages,
      { role: 'user', content: 'next request' }, { role: 'assistant', content: 'next answer' },
      { role: 'user', content: 'third request' }, { role: 'assistant', content: 'next answer' }], 100))
    window.dispatchEvent(new Event(MODEL_SETTINGS_EVENT))
    expect(store.nextContextTokens).toBeNull()
  })

  it('explains insufficient savings and estimates original input without saving a checkpoint', async () => {
    vi.spyOn(chatApi, 'compactContext').mockResolvedValue({ ...result, status: 'unchanged',
      metrics: { reasonCode: 'INSUFFICIENT_SAVINGS' } })
    const store = ready()
    await store.compactContext(settings)
    expect(store.compactionNotice).toContain('无需压缩')
    expect(store.nextContextTokens).toBe(estimateContextInput([
      { role: 'user', content: 'preserve REST' }, { role: 'assistant', content: 'agreed' }], 100))
    respond()
    await store.sendMessageStream('continue', 'default', settings)
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]!.body as string).context).toBeUndefined()
  })

  it('distinguishes Provider failure from invalid structured summaries', async () => {
    const compact = vi.spyOn(chatApi, 'compactContext').mockResolvedValue({ ...result,
      status: 'failed_passthrough', metrics: { failureCode: 'SUMMARY_PROVIDER_FAILED' } })
    const store = ready()
    await store.compactContext(settings)
    expect(store.compactionNotice).toContain('摘要模型调用失败')
    compact.mockResolvedValue({ ...result, status: 'failed_passthrough',
      metrics: { failureCode: 'SUMMARY_INVALID_SCHEMA' } })
    await store.compactContext(settings)
    expect(store.compactionNotice).toContain('有效的结构化摘要')
  })

  it('preserves a useful server error in the compaction notice', async () => {
    vi.spyOn(chatApi, 'compactContext').mockRejectedValue({ response: { data: {
      detail: { message: '压缩不可用，请检查模型窗口配置及 Node 运行环境' }
    } } })
    const store = ready()
    await expect(store.compactContext(settings)).rejects.toBeDefined()
    expect(store.compactionNotice).toContain('模型窗口配置及 Node')
    expect(store.loading).toBe(false)
  })
})
