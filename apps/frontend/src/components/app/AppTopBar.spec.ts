import { mount, flushPromises } from '@vue/test-utils'
import { createWebHistory, createRouter, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AppTopBar from './AppTopBar.vue'
import { installCommandKeybindings } from '@/workbench/core/commands'

const platformState = vi.hoisted(() => ({ desktop: false }))

vi.mock('@/platform', () => ({
  LOCAL_REQUEST_HEADERS: { 'X-Zhiyi-Local-Request': '1' },
  isDesktop: () => platformState.desktop,
  platform: {
    get platform() { return platformState.desktop ? 'desktop' : 'web' },
    get dragRegionProps() { return platformState.desktop ? { 'data-electron-drag-region': '' } : {} }
  }
}))

vi.mock('@/services/api/agentos', () => ({
  agentosApi: {
    listMissions: vi.fn(async () => ({
      items: [
        { missionId: 'mission_1', title: '第一个任务', runCount: 2, latestRunId: 'run_9' },
        { missionId: 'mission_2', title: '**强调**标题', runCount: 0, latestRunId: null }
      ],
      total: 2
    }))
  }
}))

const routes = [
  { path: '/', component: { template: '<div />' } },
  { path: '/agentos/acg', component: { template: '<div />' } },
  { path: '/history', component: { template: '<div />' } }
]

const mountTopBar = async (props: Record<string, unknown> = {}): Promise<{ wrapper: ReturnType<typeof mount>; router: Router }> => {
  // 用 web history：memory history 不向 state 写 position，组件的
  // 上一步/下一步禁用态在真实浏览器里靠 history.state.position 对账。
  const router = createRouter({
    history: createWebHistory(),
    routes
  })
  await router.push('/')
  await router.isReady()

  const wrapper = mount(AppTopBar, {
    props: {
      ...props
    },
    global: {
      plugins: [router],
      stubs: {
        'el-icon': { template: '<span><slot /></span>' }
      }
    }
  })
  await flushPromises()
  return { wrapper, router }
}

describe('AppTopBar', () => {
  let disposeKeybindings: (() => void) | null = null
  beforeEach(() => {
    // Ctrl/Cmd+K 由命令表派发，组件只负责注册命令。
    disposeKeybindings = installCommandKeybindings()
  })
  afterEach(() => {
    disposeKeybindings?.()
    disposeKeybindings = null
  })

  it('renders the shell context and command center', async () => {
    const { wrapper } = await mountTopBar()

    expect(wrapper.find('[aria-label="应用工作栏"]').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('知弈工作台')
    expect(wrapper.get('input').attributes('placeholder')).toBe('搜索任务、步骤、运行或命令')
  })

  it('emits shell actions and clears the command on Escape', async () => {
    const { wrapper } = await mountTopBar()

    await wrapper.findAll('.app-topbar__menu-links button')[1].trigger('click')
    await wrapper.get('input').setValue('trace')
    await wrapper.get('input').trigger('keydown.esc')

    expect(wrapper.emitted('navigate')).toEqual([['/agentos/resources']])
    expect(wrapper.get('input').element).toHaveProperty('value', '')
  })

  it('opens the projects dropdown, lands on the hub, and routes through its menu items', async () => {
    const { wrapper } = await mountTopBar()

    await wrapper.get('[aria-haspopup="menu"]').trigger('click')
    expect(wrapper.emitted('navigate')).toEqual([['/agentos/projects']])
    const menu = wrapper.get('[role="menu"]')
    expect(menu.text()).toContain('新建 Mission')
    expect(menu.text()).toContain('打开 Mission')

    await menu.findAll('[role="menuitem"]')[1].trigger('click')
    const events = wrapper.emitted('navigate')
    expect(events).toHaveLength(2)
    expect(events![1]).toEqual(['/agentos/acg'])
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
  })

  it('closes the projects dropdown on Escape and outside pointerdown', async () => {
    const { wrapper } = await mountTopBar()
    const trigger = wrapper.get('[aria-haspopup="menu"]')

    await trigger.trigger('click')
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)

    await trigger.trigger('click')
    expect(wrapper.find('[role="menu"]').exists()).toBe(true)
    // 真实外点落在 body 元素上；直接派发到 window 会让 target 非 Node，绕过组件防御分支
    document.body.dispatchEvent(new MouseEvent('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
  })

  it('opens the recent-missions submenu and enters a mission directly', async () => {
    const { wrapper } = await mountTopBar()

    await wrapper.get('[aria-haspopup="menu"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="menu"][aria-label="项目操作"]').text()).toContain('最近 Mission')

    await wrapper.get('[data-menu-submenu-trigger]').trigger('click')
    await flushPromises()

    const submenu = wrapper.get('[role="menu"][aria-label="最近 Mission"]')
    const items = submenu.findAll('[role="menuitem"]')
    expect(items).toHaveLength(3)
    expect(items[0].text()).toContain('第一个任务')
    expect(items[0].text()).toContain('2 次运行')

    await items[0].trigger('click')
    const events = wrapper.emitted('navigate')
    expect(events![events!.length - 1]).toEqual(['/agentos/missions/mission_1/workspace?runId=run_9'])
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
  })

  it('reopens the recent-missions submenu instantly from cache and routes 更多… to the full list', async () => {
    const { wrapper } = await mountTopBar()

    await wrapper.get('[aria-haspopup="menu"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-menu-submenu-trigger]').trigger('click')
    await flushPromises()
    // 收起（再点触发器即关闭整套）后重新展开
    await wrapper.get('[aria-haspopup="menu"]').trigger('click')
    await wrapper.get('[aria-haspopup="menu"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-menu-submenu-trigger]').trigger('click')
    await flushPromises()

    // 缓存命中：任务行已在，不出现加载/错误提示行
    const submenu = wrapper.get('[role="menu"][aria-label="最近 Mission"]')
    expect(submenu.text()).toContain('第一个任务')
    expect(submenu.find('.app-topbar__dropdown-note').exists()).toBe(false)

    const items = submenu.findAll('[role="menuitem"]')
    expect(items).toHaveLength(3)
    await items[2].trigger('click')
    const events = wrapper.emitted('navigate')
    expect(events![events!.length - 1]).toEqual(['/agentos/acg'])
    expect(wrapper.find('[role="menu"]').exists()).toBe(false)
  })

  it('focuses the command center with Ctrl/Cmd+K', async () => {
    const { wrapper } = await mountTopBar()
    const input = wrapper.get('input').element as HTMLInputElement
    const focusSpy = vi.spyOn(input, 'focus')

    window.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'k',
      code: 'KeyK',
      ctrlKey: true,
      bubbles: true,
      cancelable: true
    }))
    await flushPromises()

    expect(focusSpy).toHaveBeenCalledTimes(1)
  })

  it('toggles the command menu closed on the second Ctrl/Cmd+K', async () => {
    const { wrapper } = await mountTopBar()
    const input = wrapper.get('input')
    const blurSpy = vi.spyOn(input.element, 'blur')

    await input.trigger('focus')
    await input.setValue('资源')
    expect(wrapper.find('.app-command-menu').exists()).toBe(true)

    window.dispatchEvent(new KeyboardEvent('keydown', {
      key: 'k',
      code: 'KeyK',
      ctrlKey: true,
      bubbles: true,
      cancelable: true
    }))
    await flushPromises()

    expect(blurSpy).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.app-command-menu').exists()).toBe(false)
    expect(input.element).toHaveProperty('value', '')
  })

  it('filters navigation commands and navigates with Enter', async () => {
    const { wrapper } = await mountTopBar()
    const input = wrapper.get('input')

    await input.trigger('focus')
    await input.setValue('资源')

    const option = wrapper.get('[role="option"]')
    expect(option.text()).toContain('资源中心')

    await input.trigger('keydown', { key: 'Enter' })

    expect(wrapper.emitted('navigate')).toEqual([['/agentos/resources']])
    expect(input.element).toHaveProperty('value', '')
  })

  it('keeps command results clickable while the input loses focus', async () => {
    const { wrapper } = await mountTopBar()
    const input = wrapper.get('input')

    await input.trigger('focus')
    await input.setValue('运行')
    const option = wrapper.get('[role="option"]')

    await option.trigger('mousedown')
    await option.trigger('click')

    expect(wrapper.emitted('navigate')).toEqual([['/history']])
  })

  it('keeps the logo decorative: the rail is permanent and there is no navigation toggle', async () => {
    const { wrapper } = await mountTopBar()

    expect(wrapper.find('[aria-label="展开导航"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="收起导航"]').exists()).toBe(false)
    expect(wrapper.get('.app-topbar__brand-zone .app-topbar__logo img').exists()).toBe(true)
  })

  it('removes the requested topbar action group', async () => {
    const { wrapper } = await mountTopBar()

    expect(wrapper.find('.app-topbar__actions').exists()).toBe(false)
    expect(wrapper.find('[aria-label="切换布局"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="打开设置"]').exists()).toBe(false)
    expect(wrapper.find('[aria-label="打开用户中心"]').exists()).toBe(false)
  })

  it('keeps the web shell free of desktop window chrome', async () => {
    const { wrapper } = await mountTopBar()

    expect(wrapper.find('.desktop-window-controls').exists()).toBe(false)
    expect(wrapper.find('[aria-label="关闭"]').exists()).toBe(false)
    expect(wrapper.find('[data-electron-drag-region]').exists()).toBe(false)
  })

  it('keeps every topbar surface draggable in the desktop shell', async () => {
    // 桌面拖动区只认被点中的元素：网格包裹层若不带 drag-region，
    // 顶栏空白处（含窗口控件两侧）按下时 target 落在包裹层上，窗口就拖不动了。
    platformState.desktop = true
    try {
      const { wrapper } = await mountTopBar()

      const surfaces = [
        '.app-topbar',
        '.app-topbar__left',
        '.app-topbar__brand-zone',
        '.app-topbar__menu-links',
        '.app-topbar__command',
        '.app-topbar__right'
      ]
      for (const selector of surfaces) {
        expect(wrapper.get(selector).attributes('data-electron-drag-region')).toBe('')
      }
      wrapper.unmount()
    } finally {
      platformState.desktop = false
    }
  })

  it('starts with both history buttons disabled', async () => {
    const { wrapper } = await mountTopBar()

    expect(wrapper.get('[aria-label="上一步"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[aria-label="下一步"]').attributes('disabled')).toBeDefined()
  })

  // jsdom 不派发 popstate：先把 location/state 改写回目标项，再手动派发事件
  // （vue-router 的 popstate 处理器从 window.location 读目标路由）。
  const popHistoryTo = async (state: object, path: string) => {
    window.history.replaceState(state, '', path)
    window.dispatchEvent(new PopStateEvent('popstate', { state }))
    await flushPromises()
  }

  it('delegates the history buttons to the router', async () => {
    const rootState = JSON.parse(JSON.stringify(window.history.state))
    const { wrapper, router } = await mountTopBar()
    const back = wrapper.get('[aria-label="上一步"]')
    const forward = wrapper.get('[aria-label="下一步"]')
    const backSpy = vi.spyOn(router, 'back').mockImplementation(() => {})
    const forwardSpy = vi.spyOn(router, 'forward').mockImplementation(() => {})

    await router.push('/agentos/acg')
    await flushPromises()
    expect(back.attributes('disabled')).toBeUndefined()

    await back.trigger('click')
    expect(backSpy).toHaveBeenCalledTimes(1)

    await popHistoryTo(rootState, '/')
    expect(forward.attributes('disabled')).toBeUndefined()
    await forward.trigger('click')
    expect(forwardSpy).toHaveBeenCalledTimes(1)
  })

  it('tracks the history position to toggle the buttons', async () => {
    const rootState = JSON.parse(JSON.stringify(window.history.state))
    const { wrapper, router } = await mountTopBar()
    const back = wrapper.get('[aria-label="上一步"]')
    const forward = wrapper.get('[aria-label="下一步"]')

    expect(back.attributes('disabled')).toBeDefined()
    expect(forward.attributes('disabled')).toBeDefined()

    await router.push('/agentos/acg')
    await flushPromises()
    expect(back.attributes('disabled')).toBeUndefined()
    expect(forward.attributes('disabled')).toBeDefined()

    await router.push('/history?tab=acg')
    await flushPromises()
    await popHistoryTo(rootState, '/')
    expect(router.currentRoute.value.fullPath).toBe('/')
    expect(back.attributes('disabled')).toBeDefined()
    expect(forward.attributes('disabled')).toBeUndefined()
  })
})
