import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LandingView from './LandingView.vue'

const platformState = vi.hoisted(() => ({ desktop: false }))

vi.mock('@/platform', () => ({
  isDesktop: () => platformState.desktop,
  apiUrl: (path: string) => path,
  platform: {
    get platform() { return platformState.desktop ? 'desktop' : 'web' },
    get dragRegionProps() { return platformState.desktop ? { 'data-tauri-drag-region': '' } : {} }
  }
}))

vi.mock('@/views/LoginView.vue', () => ({
  default: {
    name: 'LoginView',
    template: '<div data-testid="embedded-auth">登录注册窗口</div>'
  }
}))

vi.mock('@/components/landing/GlassConstellation.vue', () => ({
  default: {
    name: 'GlassConstellation',
    template: '<div data-testid="glass-constellation">动画组件</div>'
  }
}))

describe('LandingView', () => {
  beforeEach(() => {
    platformState.desktop = false
    localStorage.clear()
    sessionStorage.clear()
  })

  const mountLanding = async (initialPath = '/') => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: LandingView },
        { path: '/login', component: { template: '<div>认证页</div>' } },
        { path: '/chat', component: { template: '<div>工作台</div>' } }
      ]
    })
    await router.push(initialPath)
    await router.isReady()
    const wrapper = mount(LandingView, {
      global: {
        plugins: [router, createPinia()],
        stubs: {
          'el-icon': { template: '<span><slot /></span>' }
        }
      }
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    return { router, wrapper }
  }

  it('把主 CTA 收敛到单一登录路由并带上原目标', async () => {
    const { router, wrapper } = await mountLanding()

    expect(wrapper.find('[data-testid="glass-constellation"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="embedded-auth"]').exists()).toBe(false)

    await wrapper.get('[data-testid="landing-cta"]').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/chat')
    expect(wrapper.find('[data-testid="glass-constellation"]').exists()).toBe(true)
  })

  it('exposes an accessible public theme toggle', async () => {
    const { wrapper } = await mountLanding()

    const toggle = wrapper.get('[data-testid="landing-theme-toggle"]')
    expect(toggle.attributes('aria-label')).toBe('切换到黑暗模式')
    expect(toggle.attributes('title')).toBe('切换到黑暗模式')
    expect(wrapper.find('.landing-view').classes()).not.toContain('is-theme-dark')
  })

  it('末屏 CTA 同样跳登录路由，不改变介绍页的滑动位置', async () => {
    const { router, wrapper } = await mountLanding()

    await wrapper.get('.landing-nav a[href="#about"]').trigger('click')
    await flushPromises()
    await wrapper.get('.landing-cta--small').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/login')
    expect(router.currentRoute.value.query.redirect).toBe('/chat')
    expect(wrapper.find('[data-testid="embedded-auth"]').exists()).toBe(false)
  })

  it('opens embedded auth when requested by the landing query', async () => {
    const { wrapper } = await mountLanding('/?auth=1&redirect=/chat')

    expect(wrapper.find('[data-testid="embedded-auth"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="glass-constellation"]').exists()).toBe(false)
  })

  it('presents a focused light landing sequence without legacy floating chrome', async () => {
    const { wrapper } = await mountLanding()

    expect(wrapper.text()).toContain('让智能体成为协作者')
    expect(wrapper.find('.landing-header__login').exists()).toBe(false)
    expect(wrapper.findAll('.capability-card')).toHaveLength(0)
    expect(wrapper.findAll('.landing-orbit-label')).toHaveLength(0)
    expect(wrapper.find('[data-testid="landing-scroll-hint"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="glass-constellation"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-testid^="landing-page-"]')).toHaveLength(4)
    expect(wrapper.findAll('.landing-info-card')).toHaveLength(5)
    expect(wrapper.text()).toContain('从目标，到结果')
    expect(wrapper.text()).toContain('统一管理模型与工具')
    expect(wrapper.text()).toContain('二龙山')
    expect(wrapper.text()).toContain('游击队')
    expect(wrapper.text()).toContain('PHONE / 电话')
    expect(wrapper.text()).toContain('EMAIL / 邮箱')
  })

  it('moves exactly one content page for each meaningful wheel gesture', async () => {
    const { wrapper } = await mountLanding()

    expect(wrapper.find('a[href="#home"]').classes()).toContain('is-active')

    await wrapper.trigger('wheel', { deltaY: 120 })
    expect(wrapper.find('a[href="#features"]').classes()).toContain('is-active')
    expect(wrapper.find('.landing-track').attributes('style')).toContain('translate3d(0px, -25%, 0px)')

    await wrapper.trigger('wheel', { deltaY: 120 })
    expect(wrapper.find('a[href="#features"]').classes()).toContain('is-active')
  })

  it('keeps the page web-only in the browser shell: no desktop chrome class or drag region', async () => {
    const { wrapper } = await mountLanding()

    expect(wrapper.find('.landing-view').classes()).not.toContain('is-desktop-shell')
    expect(wrapper.find('.landing-header').attributes('data-tauri-drag-region')).toBeUndefined()
  })

  it('mounts the window drag region on the header when running in the desktop shell', async () => {
    platformState.desktop = true
    const { wrapper } = await mountLanding()

    expect(wrapper.find('.landing-view').classes()).toContain('is-desktop-shell')
    expect(wrapper.find('.landing-header').attributes('data-tauri-drag-region')).toBe('')
  })

  it('keeps the active section in the router hash for direct return navigation', async () => {
    const { router, wrapper } = await mountLanding()

    await wrapper.findAll('.landing-nav a')[1].trigger('click')
    await flushPromises()

    expect(wrapper.find('a[href="#features"]').classes()).toContain('is-active')
    expect(wrapper.find('.landing-track').attributes('style')).toContain('translate3d(0px, -25%, 0px)')
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.hash).toBe('#features')
  })

  it('opens directly on the section encoded in the landing hash', async () => {
    const { router, wrapper } = await mountLanding('/#ecosystem')

    expect(router.currentRoute.value.hash).toBe('#ecosystem')
    expect(wrapper.find('a[href="#ecosystem"]').classes()).toContain('is-active')
    expect(wrapper.find('.landing-track').attributes('style')).toContain('translate3d(0px, -50%, 0px)')
  })

  it('keeps the brand link a SPA navigation to the landing route', async () => {
    const { router, wrapper } = await mountLanding()

    await wrapper.get('.landing-brand').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/')
  })
})
