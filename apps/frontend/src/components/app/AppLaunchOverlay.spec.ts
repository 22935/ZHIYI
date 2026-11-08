import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AppLaunchOverlay from './AppLaunchOverlay.vue'

const SESSION_KEY = 'kinlin.launchOverlay.v1'
const overlay = () => document.body.querySelector('[data-testid="app-launch-overlay"]')
const enterButton = () => document.body.querySelector<HTMLButtonElement>('[data-testid="app-launch-enter"]')

let wrapper: VueWrapper | null = null

/** visible 在 onMounted 才置位，Teleport 内容需等一次渲染微任务才进 body。 */
const mountOverlay = async (): Promise<void> => {
  wrapper = mount(AppLaunchOverlay, { attachTo: document.body })
  await flushPromises()
  await nextTick()
}

/** Transition 的 leave 阶段同样要等渲染微任务结束。 */
const settle = async (): Promise<void> => {
  await flushPromises()
  await nextTick()
  await flushPromises()
}

beforeEach(() => {
  document.body.innerHTML = ''
  sessionStorage.clear()
  localStorage.removeItem('token')
  window.history.replaceState({}, '', '/')
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn()
  }))
})

afterEach(async () => {
  wrapper?.unmount()
  wrapper = null
  await settle()
  document.body.innerHTML = ''
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('AppLaunchOverlay', () => {
  it('冷启动时显示品牌启动页并标记本会话已展示', async () => {
    await mountOverlay()

    expect(overlay()).not.toBeNull()
    expect(document.body.textContent).toContain('知弈 AgentOS')
    expect(document.body.textContent).toContain('无需账号密码')
    expect(document.body.textContent).toContain('进入工作台')
    expect(sessionStorage.getItem(SESSION_KEY)).toBe('1')
  })

  it('不触碰登录态：不写 token、不发请求、不改路由', async () => {
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    const hashBefore = window.location.hash
    await mountOverlay()

    expect(localStorage.getItem('token')).toBeNull()
    expect(fetchSpy).not.toHaveBeenCalled()
    expect(window.location.hash).toBe(hashBefore)
    expect(window.location.pathname).toBe('/')
  })

  it('同一浏览器会话只显示一次', async () => {
    sessionStorage.setItem(SESSION_KEY, '1')
    await mountOverlay()
    expect(overlay()).toBeNull()
  })

  it('?splash=1 可强制重现，便于验收', async () => {
    sessionStorage.setItem(SESSION_KEY, '1')
    window.history.replaceState({}, '', '/?splash=1')
    await mountOverlay()
    expect(overlay()).not.toBeNull()
  })

  it('点击「进入工作台」立即跳过', async () => {
    await mountOverlay()
    expect(enterButton()).not.toBeNull()

    enterButton()?.click()
    await settle()
    expect(enterButton()).toBeNull()
  })

  it('按 Esc 立即跳过', async () => {
    await mountOverlay()
    expect(enterButton()).not.toBeNull()

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await settle()
    expect(enterButton()).toBeNull()
  })

  it('到时自动淡出，无需用户操作', async () => {
    vi.useFakeTimers()
    await mountOverlay()
    expect(overlay()).not.toBeNull()

    await vi.advanceTimersByTimeAsync(2600)
    await settle()
    expect(enterButton()).toBeNull()
  })

  it('reduced-motion 下缩短等待时间', async () => {
    vi.useFakeTimers()
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn()
    }))
    await mountOverlay()
    expect(overlay()).not.toBeNull()

    await vi.advanceTimersByTimeAsync(699)
    await settle()
    expect(enterButton()).not.toBeNull()

    await vi.advanceTimersByTimeAsync(1)
    await settle()
    expect(enterButton()).toBeNull()
  })
})
