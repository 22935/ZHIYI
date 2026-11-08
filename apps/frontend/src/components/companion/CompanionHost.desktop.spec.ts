import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CompanionHost from './CompanionHost.vue'

vi.mock('@/services/api/workflow', () => ({
  workflowApi: {
    getWorkflowProgress: vi.fn(async (runId: string) => ({
      runId, status: 'running', phase: '执行中', percent: 50,
      totalSteps: 4, completedSteps: 2, activeStepIds: ['step_3'],
      waitingReviewSteps: 0, failedSteps: 0, message: ''
    }))
  }
}))

const query = (selector: string): HTMLElement | null => document.body.querySelector(selector)

const buildBridge = () => ({
  publishState: vi.fn(async (_snapshot: unknown) => undefined),
  notifyIfBackground: vi.fn(async (_title: string, _body: string) => undefined),
  onTrayAction: vi.fn((_cb: (action: string) => void) => () => undefined)
})

let bridge: ReturnType<typeof buildBridge>
let trayListener: ((action: string) => void) | null = null

const installBridge = (): void => {
  bridge = buildBridge()
  trayListener = null
  bridge.onTrayAction.mockImplementation((cb: (action: string) => void) => {
    trayListener = cb
    return () => { trayListener = null }
  })
  ;(window as unknown as { kinlinDesktop?: unknown }).kinlinDesktop = { companion: bridge }
}

describe('CompanionHost desktop integration', () => {
  beforeEach(() => {
    localStorage.clear()
    document.body.innerHTML = ''
    installBridge()
  })

  afterEach(() => {
    document.body.innerHTML = ''
    localStorage.clear()
    delete (window as unknown as { kinlinDesktop?: unknown }).kinlinDesktop
    vi.clearAllMocks()
  })

  it('publishes its state to the tray on mount and subscribes once', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()
    expect(bridge.publishState).toHaveBeenCalled()
    expect(bridge.publishState.mock.calls[0][0]).toMatchObject({ state: 'idle', label: '待机', quiet: false })
    expect(bridge.onTrayAction).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    expect(trayListener).toBeNull()
  })

  it('handles a tray progress action by expanding and answering with the read-only projection', async () => {
    localStorage.setItem('companion.active_run_id.v1', 'run_42')
    const wrapper = mount(CompanionHost)
    await flushPromises()
    trayListener?.('progress')
    await flushPromises()
    expect(query('[data-testid="companion-dialogue"]')).not.toBeNull()
    expect(query('[data-testid="companion-messages"]')?.textContent).toContain('2/4')
    wrapper.unmount()
  })

  it('sends high-priority events to native notifications, and quiet mode suppresses them', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()
    window.dispatchEvent(new CustomEvent('companion:run-event', {
      detail: { eventType: 'run.failed', runId: 'run_9' }
    }))
    await flushPromises()
    expect(bridge.notifyIfBackground).toHaveBeenCalledWith(
      '知宝 · 出错了', expect.stringContaining('Trace')
    )

    query('[data-testid="companion-avatar"]')?.click()
    await flushPromises()
    const quiet = query('[data-testid="companion-quiet"]') as HTMLInputElement
    quiet.checked = true
    quiet.dispatchEvent(new Event('change', { bubbles: true }))
    await flushPromises()
    expect(bridge.publishState).toHaveBeenCalledWith(expect.objectContaining({ quiet: true }))

    bridge.notifyIfBackground.mockClear()
    window.dispatchEvent(new CustomEvent('companion:run-event', {
      detail: { eventType: 'node.failed', runId: 'run_10' }
    }))
    await flushPromises()
    expect(bridge.notifyIfBackground).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('toggles with Ctrl+Shift+K and collapses with Escape', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'K', ctrlKey: true, shiftKey: true }))
    await flushPromises()
    expect(query('[data-testid="companion-dialogue"]')).not.toBeNull()
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(query('[data-testid="companion-dialogue"]')).toBeNull()
    wrapper.unmount()
  })

  it('grows affinity from a pat and shows a floating reaction bubble', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()
    query('[data-testid="companion-avatar"]')?.click()
    await flushPromises()
    const before = query('[data-testid="companion-pet-affinity"]')?.getAttribute('style') || ''
    query('[data-testid="companion-pet-pat"]')?.click()
    await flushPromises()
    expect(query('[data-testid="companion-bubble"]')?.textContent).toContain('+1 好感')
    expect(query('[data-testid="companion-pet-affinity"]')?.getAttribute('style')).not.toBe(before)
    expect(query('[data-testid="companion-pet-badges"]')?.textContent).toContain('初次见面')
    wrapper.unmount()
  })

  it('keeps the expanded panel on screen when the pet was docked left', async () => {
    localStorage.setItem('companion.position.v1', '{"right":936,"bottom":300}')
    const wrapper = mount(CompanionHost)
    await flushPromises()
    expect(query('[data-testid="companion-root"]')?.getAttribute('style')).toContain('right: 936px')

    query('[data-testid="companion-avatar"]')?.click()
    await flushPromises()
    expect(query('[data-testid="companion-root"]')?.getAttribute('style')).toContain('right: 692px')
    expect(localStorage.getItem('companion.position.v1')).toContain('"right":692')
    expect(query('[data-testid="companion-bubble"]')?.textContent).toContain('往里挪了挪')
    wrapper.unmount()
  })

  it('repairs a remembered expanded left-docked position on mount', async () => {
    localStorage.setItem('companion.expanded.v1', '1')
    localStorage.setItem('companion.position.v1', '{"right":936,"bottom":300}')
    const wrapper = mount(CompanionHost)
    await flushPromises()
    expect(query('[data-testid="companion-root"]')?.getAttribute('style')).toContain('right: 692px')
    wrapper.unmount()
  })

  it('drags the companion within the viewport and persists the position', async () => {
    const wrapper = mount(CompanionHost)
    await flushPromises()
    const avatar = query('[data-testid="companion-avatar"]') as HTMLElement
    avatar.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true, button: 0, clientX: 100, clientY: 100 }))
    window.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 160, clientY: 150 }))
    window.dispatchEvent(new MouseEvent('pointerup', { bubbles: true }))
    await flushPromises()
    expect(query('[data-testid="companion-root"]')?.getAttribute('style')).toContain('right: 888px')
    expect(query('[data-testid="companion-root"]')?.getAttribute('style')).toContain('bottom: 396px')
    // 面板最大高度依赖该变量：拖到上方时按视口剩余空间收缩，避免顶部溢出。
    expect(query('[data-testid="companion-root"]')?.getAttribute('style')).toContain('--companion-bottom: 396px')
    expect(localStorage.getItem('companion.position.v1')).toContain('"right":888')
    expect(query('[data-testid="companion-dialogue"]')).toBeNull()
    wrapper.unmount()
  })
})
