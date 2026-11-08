import { webcrypto } from 'node:crypto'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import LoginView from './LoginView.vue'
import { isAuthenticated } from '@/features/auth/authService'

let wrapper: VueWrapper | null = null

// Element Plus 的 async-validator 需要真实定时器 tick 才会渲染 .el-form-item__error。
const settle = async () => {
  for (let i = 0; i < 4; i += 1) {
    await flushPromises()
    await new Promise(resolve => setTimeout(resolve, 40))
  }
}

const mountLogin = async (path = '/login', props: { embedded?: boolean } = {}) => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: LoginView },
      { path: '/', component: { template: '<div>介绍页</div>' } },
      { path: '/chat', component: { template: '<div>工作台</div>' } },
      { path: '/history', component: { template: '<div>历史</div>' } }
    ]
  })
  await router.push(path)
  await router.isReady()
  wrapper = mount(LoginView, {
    props,
    attachTo: document.body,
    global: {
      plugins: [router, ElementPlus, createPinia()],
      stubs: { LoginAcgDemo: true }
    }
  })
  await flushPromises()
  return { router, wrapper }
}

/** Element Plus 会同时渲染两个 tab 的表单，按索引取对应面板。 */
const formAt = (index: number) => wrapper!.findAll('form')[index]
const fill = async (formIndex: number, autocomplete: string, value: string) => {
  const field = formAt(formIndex).find(`input[autocomplete="${autocomplete}"]`)
  await field.setValue(value)
}
const submitAt = async (index: number) => {
  await wrapper!.findAll('[data-testid="auth-submit"]')[index].trigger('click')
  await settle()
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  vi.stubGlobal('crypto', webcrypto)
  vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn()
  }))
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

describe('LoginView（浅色介绍页配套登录注册）', () => {
  it('渲染浅色玻璃卡片与登录/注册双 tab', async () => {
    const { wrapper: view } = await mountLogin()
    expect(view.find('[data-testid="auth-card"]').exists()).toBe(true)
    expect(view.find('.auth-intro').text()).toContain('多智能体协作')
    expect(view.get('#auth-card-title').text()).toContain('登录知弈 AgentOS')
    expect(view.text()).toContain('注册')
  })

  it('默认呈现浅色场景，并提供可访问的主题切换与返回介绍页入口', async () => {
    const { wrapper: view } = await mountLogin()
    expect(view.find('.auth-view').classes()).not.toContain('is-theme-dark')
    const toggle = view.get('[data-testid="auth-theme-toggle"]')
    expect(toggle.attributes('aria-label')).toBe('切换到黑暗模式')
    expect(view.get('.auth-brand').exists()).toBe(true)
    await toggle.trigger('click')
    await flushPromises()
    expect(view.find('.auth-view').classes()).toContain('is-theme-dark')
  })

  it('?mode=register 直接进入注册模式，页内切换不改变路由', async () => {
    const { router, wrapper: view } = await mountLogin()
    expect(view.get('#auth-card-title').text()).toContain('登录知弈 AgentOS')
    await view.findAll('.el-tabs__item')[1].trigger('click')
    await settle()
    expect(view.get('#auth-card-title').text()).toContain('创建知弈 AgentOS 账号')
    expect(router.currentRoute.value.path).toBe('/login')

    await mountLogin('/login?mode=register')
    expect(wrapper!.get('#auth-card-title').text()).toContain('创建知弈 AgentOS 账号')
  })

  it('嵌入介绍页时只保留卡片，关闭按钮发回 back', async () => {
    const { wrapper: view } = await mountLogin('/login', { embedded: true })
    expect(view.find('.auth-topbar').exists()).toBe(false)
    expect(view.find('.auth-intro').exists()).toBe(false)
    expect(view.find('.auth-footer').exists()).toBe(false)
    await view.get('[data-testid="auth-dialog-close"]').trigger('click')
    expect(view.emitted('back')).toHaveLength(1)
  })

  it('空登录表单被逐字段拦截且不建立会话', async () => {
    const { wrapper: view } = await mountLogin()
    await submitAt(0)
    expect(view.text()).toContain('请输入用户名')
    expect(view.text()).toContain('请输入密码')
    expect(isAuthenticated()).toBe(false)
  })

  it('注册时拒绝弱密码与两次输入不一致', async () => {
    const { wrapper: view } = await mountLogin('/login?mode=register')
    await fill(1, 'username', 'tester')
    await fill(1, 'email', 'tester@example.com')
    const passwords = formAt(1).findAll('input[autocomplete="new-password"]')
    await passwords[0].setValue('onlyletters')
    await passwords[1].setValue('different1')
    await submitAt(1)
    expect(view.text()).toContain('密码需同时包含字母和数字')
    expect(isAuthenticated()).toBe(false)
  })

  it('注册成功后回登录 tab 并预填账号，不自动建立会话', async () => {
    const { wrapper: view } = await mountLogin('/login?mode=register')
    await fill(1, 'username', 'tester')
    await fill(1, 'email', 'tester@example.com')
    const passwords = formAt(1).findAll('input[autocomplete="new-password"]')
    await passwords[0].setValue('agentOS2026')
    await passwords[1].setValue('agentOS2026')
    await submitAt(1)
    expect(view.get('#auth-card-title').text()).toContain('登录知弈 AgentOS')
    expect((formAt(0).find('input[autocomplete="username"]').element as HTMLInputElement).value).toBe('tester')
    expect(isAuthenticated()).toBe(false)
  })

  it('密码错误显示剩余次数，正确密码登录后跳回 redirect 目标', async () => {
    const { router, wrapper: view } = await mountLogin('/login?mode=register&redirect=%2Fhistory')
    await fill(1, 'username', 'tester')
    await fill(1, 'email', 'tester@example.com')
    const passwords = formAt(1).findAll('input[autocomplete="new-password"]')
    await passwords[0].setValue('agentOS2026')
    await passwords[1].setValue('agentOS2026')
    await submitAt(1)

    await fill(0, 'current-password', 'wrongpass1')
    await submitAt(0)
    expect(view.text()).toContain('还可尝试 4 次')
    expect(isAuthenticated()).toBe(false)

    await fill(0, 'current-password', 'agentOS2026')
    await submitAt(0)
    expect(isAuthenticated()).toBe(true)
    expect(router.currentRoute.value.path).toBe('/history')
  })

  it('品牌标记返回介绍页并保留来源锚点', async () => {
    const { router, wrapper: view } = await mountLogin('/login?from=%2F%23ecosystem')
    await view.get('.auth-brand').trigger('click')
    await settle()
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.hash).toBe('#ecosystem')
  })
})
