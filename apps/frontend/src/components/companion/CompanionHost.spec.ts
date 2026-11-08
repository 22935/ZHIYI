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

  it('is voice-first: no text input, but quick commands still create a task intent card', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()

    query('[data-testid="companion-avatar"]')?.click()
    await flushPromises()
    expect(query('[data-testid="companion-dialogue"]')).not.toBeNull()
    // 用户要求不用打字：面板里不再有文字输入框，改用麦克风与指令按钮。
    expect(query('[data-testid="companion-input"]')).toBeNull()
    expect(query('[data-testid="companion-mic"]')).not.toBeNull()

    const quick = query('[data-testid="companion-quick-task"]') as HTMLButtonElement
    quick.click()
    await flushPromises()

    const messages = query('[data-testid="companion-messages"]')?.textContent || ''
    expect(messages).toContain('帮我新建一个合同审查任务')
    expect(messages).toContain('整理成一张任务卡')
    expect(query('[data-testid="companion-card"]')?.textContent).toContain('合同审查任务')
    expect(query('[data-testid="companion-state"]')?.textContent).toContain('思考中')

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
