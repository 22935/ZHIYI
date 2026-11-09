import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CompanionHost from './CompanionHost.vue'
import { CUSTOMIZATION_STORAGE_KEY } from '@/features/companion/customization'
import type { RecognitionEventLike, RecognitionLike } from '@/features/companion/voice'

vi.mock('@/services/api/workflow', () => ({
  workflowApi: {
    getWorkflowProgress: vi.fn(async (runId: string) => ({
      runId, status: 'running', phase: '执行中', percent: 25,
      totalSteps: 4, completedSteps: 1, activeStepIds: ['step_2'],
      waitingReviewSteps: 0, failedSteps: 0, message: ''
    }))
  }
}))

const query = (selector: string): HTMLElement | null => document.body.querySelector(selector)

let activeRecognition: RecognitionLike | null = null

class FakeSpeechRecognition implements RecognitionLike {
  lang = ''
  continuous = false
  interimResults = false
  onresult: ((event: RecognitionEventLike) => void) | null = null
  onerror: ((event: { error?: string }) => void) | null = null
  onend: (() => void) | null = null
  constructor() { activeRecognition = this }
  start(): void { /* browser would open the microphone here */ }
  stop(): void { this.onend?.() }
  abort(): void { /* no-op */ }
}

const installRecognition = (): void => {
  (window as unknown as Record<string, unknown>).SpeechRecognition = FakeSpeechRecognition
}

const say = (text: string): void => {
  activeRecognition?.onresult?.({
    resultIndex: 0,
    results: [{ 0: { transcript: text }, isFinal: true }]
  })
}

const open = async () => {
  const wrapper = mount(CompanionHost)
  await flushPromises()
  query('[data-testid="companion-avatar"]')?.click()
  await flushPromises()
  return wrapper
}

describe('CompanionHost voice-first interaction', () => {
  beforeEach(() => {
    localStorage.clear()
    document.body.innerHTML = ''
    activeRecognition = null
    installRecognition()
  })

  afterEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
    delete (window as unknown as Record<string, unknown>).SpeechRecognition
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition
    vi.clearAllMocks()
  })

  it('turns a spoken sentence into a task intent card without any typing', async () => {
    const wrapper = await open()
    expect(query('[data-testid="companion-input"]')).toBeNull()
    query('[data-testid="companion-mic"]')?.click()
    await flushPromises()
    expect(activeRecognition).not.toBeNull()

    say('帮我新建一个合同审查任务')
    await flushPromises()
    const messages = query('[data-testid="companion-messages"]')?.textContent || ''
    expect(messages).toContain('帮我新建一个合同审查任务')
    expect(messages).toContain('整理成一张任务卡')
    expect(query('[data-testid="companion-card"]')?.textContent).toContain('合同审查任务')
    wrapper.unmount()
  })

  it('routes spoken control phrases to panel actions instead of small talk', async () => {
    const wrapper = await open()
    query('[data-testid="companion-mic"]')?.click()
    await flushPromises()
    say('把面板收起来')
    await flushPromises()

    expect(query('[data-testid="companion-dialogue"]')).toBeNull()
    expect(query('[data-testid="companion-bubble"]')?.textContent).toContain('退到角落')
    wrapper.unmount()
  })

  it('shows an honest fallback when the host has no speech recognition', async () => {
    delete (window as unknown as Record<string, unknown>).SpeechRecognition
    const wrapper = await open()
    query('[data-testid="companion-mic"]')?.click()
    await flushPromises()

    expect(query('[data-testid="companion-voice-subtitle"]')?.textContent)
      .toContain('不能语音输入')
    // 快捷指令已按需求移除：降级提示不再指向不存在的按钮。
    expect(query('[data-testid="companion-quick-progress"]')).toBeNull()
    wrapper.unmount()
  })

  it('wakes up from its name and takes the rest of the sentence in one shot', async () => {
    const wrapper = await open()
    // 点头像的那次手势已布防唤醒监听，当前活跃的识别实例就是唤醒会话。
    say('知宝，帮我新建一个合同审查任务')
    await flushPromises()

    const messages = query('[data-testid="companion-messages"]')?.textContent || ''
    expect(messages).toContain('帮我新建一个合同审查任务')
    expect(messages).toContain('整理成一张任务卡')
    expect(query('[data-testid="companion-card"]')?.textContent).toContain('合同审查任务')
    wrapper.unmount()
  })

  it('mutes voice output without disabling the rest of the panel', async () => {
    const wrapper = await open()
    query('[data-testid="companion-mute"]')?.click()
    await flushPromises()
    expect(query('[data-testid="companion-mute"]')?.textContent).toBe('静音')
    expect(query('[data-testid="companion-bubble"]')?.textContent).toContain('气泡')
    expect(localStorage.getItem(CUSTOMIZATION_STORAGE_KEY)).toContain('"muted":true')
    wrapper.unmount()
  })

  it('lets the user DIY the character and keeps the new name', async () => {
    const wrapper = await open()
    // DIY 入口收进设置面板。
    query('[data-testid="companion-settings-open"]')?.click()
    await flushPromises()
    query('[data-testid="companion-diy-open"]')?.click()
    await flushPromises()
    expect(query('[data-testid="companion-customizer"]')).not.toBeNull()

    const name = query('[data-testid="companion-diy-name"]') as HTMLInputElement
    name.value = '团子'
    name.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    query('[data-testid="companion-diy-save"]')?.click()
    await flushPromises()

    expect(query('[data-testid="companion-customizer"]')).toBeNull()
    expect(query('[data-testid="companion-name"]')?.textContent).toBe('团子')
    expect(localStorage.getItem(CUSTOMIZATION_STORAGE_KEY)).toContain('团子')
    // 保存后回到设置看形象下拉：DIY 皮肤已被选上。
    query('[data-testid="companion-settings-open"]')?.click()
    await flushPromises()
    expect((query('[data-testid="companion-skin"]') as HTMLSelectElement).value)
      .toBe('companion-diy')
    wrapper.unmount()
  })

  it('wires workshop audition to the voice engine and admits when it cannot speak', async () => {
    const wrapper = await open()
    query('[data-testid="companion-settings-open"]')?.click()
    await flushPromises()
    query('[data-testid="companion-diy-open"]')?.click()
    await flushPromises()
    // 工坊只负责发意图，真正开口的是宿主持有的 VoiceEngine。
    query('[data-testid="companion-diy-audition"]')?.click()
    await flushPromises()
    // jsdom 没有 speechSynthesis：接线通了，但绝不能假装试听成功。
    expect(query('[data-testid="companion-bubble"]')?.textContent).toContain('不能试听')
    wrapper.unmount()
  })
})
