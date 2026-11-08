import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'
import GlassConstellation from './GlassConstellation.vue'
import { GROK_META } from '@/lib/grok-character'

// 控制台暴露 39 个引擎状态 + 3 个一次性动作（转一圈/跳一下/粒子）。
const ENGINE_STATE_COUNT = GROK_META.groups.reduce((total, group) => total + group.states.length, 0)
const ONE_SHOT_COUNT = 3

describe('GlassConstellation', () => {
  const mountAgent = () => mount(GlassConstellation, {
    global: { plugins: [createPinia()] }
  })

  it('exposes a controllable color agent visual for the landing hero', () => {
    const wrapper = mountAgent()

    expect(wrapper.find('[data-testid="glass-constellation"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="agent-avatar"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid="agent-shape-option"]')).toHaveLength(18)
    expect(wrapper.findAll('[data-testid="agent-action-option"]')).toHaveLength(ENGINE_STATE_COUNT + ONE_SHOT_COUNT)
    expect(wrapper.findAll('[data-testid="agent-color-option"]')).toHaveLength(11)
    expect(wrapper.get('[data-testid="agent-shape-option"][aria-label="切换为流体"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-testid="agent-color-option"][aria-label="切换为紫晶"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.find('[data-testid="agent-voice-toggle"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('builds the engine character inside the avatar svg', () => {
    const wrapper = mountAgent()

    const avatar = wrapper.get('[data-testid="agent-avatar"]')
    // 引擎绘制循环每帧以 toFixed(2) 重写 viewBox，数值恒定、格式带小数。
    expect(avatar.attributes('viewBox')).toBe('-15.00 -15.00 259.00 259.00')
    expect(avatar.attributes('aria-label')).toContain('紫晶流体')
    expect(avatar.findAll('path').length).toBeGreaterThan(2)
    wrapper.unmount()
  })

  it('keeps pointer gaze enabled by default and exposes a working toggle', async () => {
    const wrapper = mountAgent()

    await wrapper.get('[data-testid="agent-avatar-trigger"]').trigger('click')
    await wrapper.get('[data-testid="agent-control-tab-actions"]').trigger('click')

    const followButton = wrapper.get('[aria-label="跟随指针"]')
    expect(followButton.attributes('aria-pressed')).toBe('true')

    await followButton.trigger('click')
    expect(followButton.attributes('aria-pressed')).toBe('false')

    await followButton.trigger('click')
    expect(followButton.attributes('aria-pressed')).toBe('true')
    wrapper.unmount()
  })

  it('changes shape, color, and state from the visible controls', async () => {
    const wrapper = mountAgent()

    await wrapper.get('[data-testid="agent-shape-option"][aria-label="切换为水滴"]').trigger('click')
    await wrapper.get('[data-testid="agent-color-option"][aria-label="切换为赤焰"]').trigger('click')
    await wrapper.findAll('[data-testid="agent-action-option"]')
      .find(button => button.text() === '思考中')?.trigger('click')

    expect(wrapper.get('[data-testid="agent-shape-option"][aria-label="切换为水滴"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-testid="agent-color-option"][aria-label="切换为赤焰"]').attributes('aria-pressed')).toBe('true')
    expect(wrapper.get('[data-testid="agent-avatar"]').attributes('aria-label')).toContain('赤焰水滴')
    expect(wrapper.get('[data-testid="agent-avatar"]').attributes('aria-label')).toContain('思考中')
    expect(wrapper.find('.agent-stage__status').text()).toContain('思考中')
    wrapper.unmount()
  })

  it('plays one-shot tricks on top of the current state', async () => {
    const wrapper = mountAgent()

    await wrapper.findAll('[data-testid="agent-action-option"]')
      .find(button => button.text() === '跳一下')?.trigger('click')
    expect(wrapper.find('.agent-stage__status').text()).toContain('弹跳中')

    await wrapper.findAll('[data-testid="agent-action-option"]')
      .find(button => button.text() === '转一圈')?.trigger('click')
    expect(wrapper.find('.agent-stage__status').text()).toContain('旋转中')
    wrapper.unmount()
  })

  it('returns to the login rotation loop on demand', async () => {
    const wrapper = mountAgent()

    await wrapper.findAll('[data-testid="agent-action-option"]')
      .find(button => button.text() === '睡着了')?.trigger('click')
    expect(wrapper.get('[data-testid="agent-avatar"]').attributes('aria-label')).toContain('睡着了')

    await wrapper.get('[aria-label="登录轮换"]').trigger('click')
    expect(wrapper.get('[aria-label="登录轮换"]').attributes('aria-pressed')).toBe('true')
    wrapper.unmount()
  })

  it('keeps the control dock collapsed until the agent is clicked', async () => {
    const wrapper = mountAgent()

    expect(wrapper.get('[data-testid="agent-controls"]').classes()).not.toContain('is-open')
    expect(wrapper.get('[data-testid="agent-avatar-trigger"]').attributes('aria-expanded')).toBe('false')

    await wrapper.get('[data-testid="agent-avatar-trigger"]').trigger('click')

    expect(wrapper.get('[data-testid="agent-controls"]').classes()).toContain('is-open')
    expect(wrapper.get('[data-testid="agent-avatar-trigger"]').attributes('aria-expanded')).toBe('true')

    await wrapper.get('[data-testid="agent-avatar-trigger"]').trigger('click')
    expect(wrapper.get('[data-testid="agent-controls"]').classes()).not.toContain('is-open')
    wrapper.unmount()
  })

  it('reports unsupported speech recognition without breaking the visual control', async () => {
    const wrapper = mountAgent()

    await wrapper.get('[data-testid="agent-voice-toggle"]').trigger('click')

    expect(wrapper.text()).toContain('当前浏览器不支持语音识别')
    wrapper.unmount()
  })

  it('uses Justin as the voice wake word before applying a command', async () => {
    const recognition = {
      lang: '',
      continuous: false,
      interimResults: false,
      onresult: null as ((event: unknown) => void) | null,
      onerror: null as (() => void) | null,
      onend: null as (() => void) | null,
      start: vi.fn(),
      stop: vi.fn()
    }
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: vi.fn(() => recognition) })
    const wrapper = mountAgent()

    await wrapper.get('[data-testid="agent-voice-toggle"]').trigger('click')
    expect(recognition.continuous).toBe(true)
    expect(wrapper.get('[data-testid="glass-constellation"]').attributes('data-voice-state')).toBe('waiting')

    recognition.onresult?.({ results: [[{ transcript: 'Justin' }]], resultIndex: 0 })
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-testid="glass-constellation"]').attributes('data-voice-state')).toBe('awake')
    expect(wrapper.text()).toContain('已唤醒')

    recognition.onresult?.({ results: [[{ transcript: '换成紫色' }]], resultIndex: 0 })
    await wrapper.vm.$nextTick()
    expect(wrapper.get('[data-testid="agent-color-option"][aria-label="切换为紫晶"]').attributes('aria-pressed')).toBe('true')

    recognition.onresult?.({ results: [[{ transcript: '弹跳起来' }]], resultIndex: 0 })
    await wrapper.vm.$nextTick()
    expect(wrapper.find('.agent-stage__status').text()).toContain('弹跳中')

    wrapper.unmount()
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: undefined })
  })

  it('keeps the landing surface when a signed-out voice conversation needs authentication', async () => {
    localStorage.removeItem('token')
    const recognition = {
      lang: '', continuous: false, interimResults: false,
      onresult: null as ((event: unknown) => void) | null,
      onerror: null as (() => void) | null,
      onend: null as (() => void) | null,
      start: vi.fn(), stop: vi.fn()
    }
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: vi.fn(() => recognition) })
    const wrapper = mountAgent()

    await wrapper.get('[data-testid="agent-voice-toggle"]').trigger('click')
    recognition.onresult?.({ results: [[{ transcript: 'Justin' }]], resultIndex: 0 })
    recognition.onresult?.({ results: [[{ transcript: '帮我分析一下这个任务' }]], resultIndex: 0 })
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('login-requested')).toBeUndefined()
    expect(wrapper.get('[data-testid="agent-conversation"]').text()).toContain('请先登录')
    wrapper.unmount()
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: undefined })
  })

  it('emits natural-language speech after Justin wakes the agent', async () => {
    localStorage.setItem('token', 'test-token')
    const recognition = {
      lang: '', continuous: false, interimResults: false,
      onresult: null as ((event: unknown) => void) | null,
      onerror: null as (() => void) | null,
      onend: null as (() => void) | null,
      start: vi.fn(), stop: vi.fn()
    }
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: vi.fn(() => recognition) })
    const wrapper = mountAgent()

    await wrapper.get('[data-testid="agent-voice-toggle"]').trigger('click')
    recognition.onresult?.({ results: [[{ transcript: 'Justin' }]], resultIndex: 0 })
    recognition.onresult?.({ results: [[{ transcript: '帮我分析一下这个任务' }]], resultIndex: 0 })
    await wrapper.vm.$nextTick()

    expect(wrapper.emitted('voice-message')?.[0]).toEqual(['帮我分析一下这个任务'])
    wrapper.unmount()
    localStorage.removeItem('token')
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: undefined })
  })

  it('renders the authenticated backend stream in the Justin conversation bubble', async () => {
    localStorage.setItem('token', 'test-token')
    const recognition = {
      lang: '', continuous: false, interimResults: false,
      onresult: null as ((event: unknown) => void) | null,
      onerror: null as (() => void) | null,
      onend: null as (() => void) | null,
      start: vi.fn(), stop: vi.fn()
    }
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: vi.fn(() => recognition) })
    // 当前 SSE 契约以空行分帧，帧内是 { event, data } 信封。
    const chunks = [
      `data: ${JSON.stringify({ event: 'content_delta', data: { delta: '这是后端回复' } })}\n\n`,
      `data: ${JSON.stringify({ event: 'done', data: { contextId: 'ctx-justin', status: 'completed' } })}\n\n`
    ]
    let chunkIndex = 0
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      headers: { get: () => null },
      body: {
        getReader: () => ({
          read: async () => chunkIndex < chunks.length
            ? { done: false, value: new TextEncoder().encode(chunks[chunkIndex++]) }
            : { done: true, value: undefined }
        })
      }
    })))
    const wrapper = mountAgent()

    await wrapper.get('[data-testid="agent-voice-toggle"]').trigger('click')
    recognition.onresult?.({ results: [[{ transcript: 'Justin 帮我分析一下' }]], resultIndex: 0 })
    await flushPromises()

    expect(wrapper.get('[data-testid="agent-conversation"]').text()).toContain('这是后端回复')
    wrapper.unmount()
    vi.unstubAllGlobals()
    localStorage.removeItem('token')
    Object.defineProperty(window, 'SpeechRecognition', { configurable: true, value: undefined })
  })
})
