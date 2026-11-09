import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CompanionHost from './CompanionHost.vue'
import { COMPANION_SKIN_STORAGE_KEY } from '@/features/companion/skins'

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

describe('CompanionHost', () => {
  beforeEach(() => {
    localStorage.clear()
    document.body.innerHTML = ''
  })

  afterEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('mounts a collapsed avatar with the static skin and no network activity', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()

    expect(query('[data-testid="companion-root"]')).not.toBeNull()
    expect(query('[data-testid="companion-avatar"] svg')).not.toBeNull()
    expect(query('[data-testid="companion-dialogue"]')).toBeNull()
    expect(query('[data-testid="companion-avatar"]')?.getAttribute('aria-expanded')).toBe('false')

    wrapper.unmount()
    expect(query('[data-testid="companion-root"]')).toBeNull()
  })

  it('is voice-first: no text input and no quick command chips, just the mic', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()

    query('[data-testid="companion-avatar"]')?.click()
    await flushPromises()
    expect(query('[data-testid="companion-dialogue"]')).not.toBeNull()
    // 用户要求不用打字：面板里没有文字输入框，也没有快捷指令按钮，
    // 说话靠麦克风或唤醒词，任务卡链路由 voice.spec 直接覆盖。
    expect(query('[data-testid="companion-input"]')).toBeNull()
    expect(query('[data-testid="companion-mic"]')).not.toBeNull()
    expect(query('[data-testid="companion-quick-task"]')).toBeNull()
    expect(query('[data-testid="companion-quick-progress"]')).toBeNull()

    wrapper.unmount()
  })

  it('moves skin switching, DIY and wake word into the settings panel', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()
    query('[data-testid="companion-avatar"]')?.click()
    await flushPromises()
    // 底部不再摆「模型回复 / 免打扰」开关：模型回复是默认档，免打扰走语音命令与托盘。
    expect(query('[data-testid="companion-model-toggle"]')).toBeNull()
    expect(query('[data-testid="companion-quiet"]')).toBeNull()

    query('[data-testid="companion-settings-open"]')?.click()
    await flushPromises()
    expect(query('[data-testid="companion-settings"]')).not.toBeNull()
    expect(query('[data-testid="companion-skin"]')).not.toBeNull()
    expect(query('[data-testid="companion-diy-open"]')).not.toBeNull()
    // 语音唤醒默认开启；这个环境没有麦克风所以是禁用态，但不能丢掉开关。
    const wake = query('[data-testid="companion-wake"]') as HTMLInputElement
    expect(wake.checked).toBe(true)
    expect(wake.disabled).toBe(true)

    wrapper.unmount()
  })

  it('maps runtime events onto the avatar state without opening a new connection', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()
    query('[data-testid="companion-avatar"]')?.click()
    await flushPromises()

    window.dispatchEvent(new CustomEvent('companion:run-event', {
      detail: { eventType: 'run.failed', runId: 'run_9' }
    }))
    await flushPromises()

    expect(query('[data-testid="companion-state"]')?.textContent).toContain('出错了')
    expect(query('[data-testid="companion-avatar"] svg')?.getAttribute('data-companion-state')).toBe('error')
    expect(query('[data-testid="companion-messages"]')?.textContent).toContain('Trace')

    window.dispatchEvent(new CustomEvent('companion:run-event', {
      detail: { eventType: 'run.failed', runId: 'run_9' }
    }))
    await flushPromises()
    expect((query('[data-testid="companion-messages"]')?.textContent || '').split('Trace')).toHaveLength(2)

    wrapper.unmount()
  })

  it('settles on the last selected skin without leaving an extra renderer behind', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()
    query('[data-testid="companion-avatar"]')?.click()
    await flushPromises()
    // 形象切换收进设置面板：先开设置才有下拉。
    query('[data-testid="companion-settings-open"]')?.click()
    await flushPromises()
    expect(query('[data-testid="companion-settings"]')).not.toBeNull()

    const select = query('[data-testid="companion-skin"]') as HTMLSelectElement
    // 连切三次：中间那次要动态 import 动效引擎，是最慢的一枪。
    // 「最后者胜」的时序语义由 switchGuard.spec 单独锁定，这里只验真实链路
    // 不会把过期渲染器留在舞台上。
    for (const id of ['companion-diy', 'companion-grok', 'companion-static']) {
      select.value = id
      select.dispatchEvent(new Event('change'))
    }
    await flushPromises()
    await flushPromises()

    expect(select.value).toBe('companion-static')
    expect(query('[data-testid="companion-avatar"]')?.querySelectorAll('svg')).toHaveLength(1)
    expect(localStorage.getItem(COMPANION_SKIN_STORAGE_KEY)).toBe('companion-static')

    wrapper.unmount()
  })
})
