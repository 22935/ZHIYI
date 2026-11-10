import { beforeEach, describe, expect, it, vi } from 'vitest'
import router from './index'
import { AUTH_ROUTE, DEFAULT_REDIRECT } from '@/features/auth/authService'
import { SESSION_KEY } from '@/features/auth/storage'

vi.mock('@/views/ChatView.vue', () => ({ default: { template: '<main>Chat</main>' } }))
vi.mock('@/views/HistoryView.vue', () => ({ default: { template: '<main>History</main>' } }))
vi.mock('@/views/ResourceCenterView.vue', () => ({ default: { template: '<main>Resources</main>' } }))
vi.mock('@/views/ResourceOverviewView.vue', () => ({ default: { template: '<main>Resource overview</main>' } }))
vi.mock('@/views/ResourceManagementView.vue', () => ({ default: { template: '<main>Resource management</main>' } }))
vi.mock('@/views/ResourceMarketplaceView.vue', () => ({ default: { template: '<main>Resource marketplace</main>' } }))
vi.mock('@/views/LoginView.vue', () => ({ default: { template: '<main>Login</main>' } }))
vi.mock('@/views/LandingView.vue', () => ({ default: { template: '<main>Landing</main>' } }))

/** 直接写入有效本机会话，避免在路由测试里跑口令派生。 */
const signIn = () => {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify({
    accountId: 'test-local-user',
    username: 'tester',
    expiresAt: Date.now() + 60_000,
    remember: false
  }))
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  signIn()
})

describe('single auth route guard', () => {
  it('未登录访问根路径展示公开介绍页', async () => {
    sessionStorage.removeItem(SESSION_KEY)
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.meta.public).toBe(true)
  })

  it('未登录访问工作区时把原目标放进 redirect', async () => {
    sessionStorage.removeItem(SESSION_KEY)
    await router.push('/history?tab=acg')
    expect(router.currentRoute.value.path).toBe(AUTH_ROUTE)
    expect(router.currentRoute.value.query.redirect).toBe('/history?tab=acg')
  })

  it('登录路由本身无需会话即可进入，并保留注册模式', async () => {
    sessionStorage.removeItem(SESSION_KEY)
    await router.push('/login?mode=register')
    expect(router.currentRoute.value.path).toBe(AUTH_ROUTE)
    expect(router.currentRoute.value.query.mode).toBe('register')
  })

  it('已登录时工作区路由直接放行', async () => {
    await router.push('/chat')
    expect(router.currentRoute.value.path).toBe(DEFAULT_REDIRECT)
  })

  it('介绍页与登录路由都标记为公开', () => {
    expect(router.getRoutes().find(route => route.path === '/')?.meta.public).toBe(true)
    expect(router.getRoutes().find(route => route.path === AUTH_ROUTE)?.meta.public).toBe(true)
  })

  it('已登录时访问登录页被送回工作台', async () => {
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe(DEFAULT_REDIRECT)
  })

  it('登录后回到安全的站内 redirect 目标', async () => {
    await router.push('/login?redirect=%2Fhistory')
    expect(router.currentRoute.value.path).toBe('/history')
  })

  it('拒绝站外 redirect，回落到默认工作台', async () => {
    await router.push('/login?redirect=%2F%2Fevil.example')
    expect(router.currentRoute.value.path).toBe(DEFAULT_REDIRECT)
  })

  it('旧登录书签不再写 token', async () => {
    sessionStorage.removeItem(SESSION_KEY)
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe(AUTH_ROUTE)
    expect(localStorage.getItem('token')).toBeNull()
  })
})

describe('user center route contract', () => {
  it('renders the user center instead of redirecting to settings', () => {
    const userRoute = router.getRoutes().find(route => route.name === 'User')

    expect(userRoute?.path).toBe('/user')
    expect(userRoute?.redirect).toBeUndefined()
    expect(userRoute?.components?.default).toBeDefined()
  })
})

describe('integrated legacy route contract', () => {
  it.each([
    ['/roles', '/agentos/resources/overview', {}],
    ['/federated-learning', '/agentos/resources/overview', {}],
    ['/federated-models', '/agentos/resources/store', { view: 'installed' }],
    ['/agentos-console', '/history', { tab: 'acg' }],
  ])('keeps %s as a redirect-only route', (legacyPath, targetPath, query) => {
    const legacyRoute = router.getRoutes().find(route => route.path === legacyPath)

    expect(legacyRoute?.component).toBeUndefined()
    expect(legacyRoute?.redirect).toBeTypeOf('function')
    expect(legacyRoute?.redirect?.({ query: {}, params: {}, path: legacyPath } as never)).toEqual({
      path: targetPath,
      query
    })
  })

  it.each([
    ['/roles?source=legacy', '/agentos/resources/overview', { source: 'legacy' }],
    ['/federated-learning?source=legacy', '/agentos/resources/overview', { source: 'legacy' }],
    ['/federated-models?source=legacy', '/agentos/resources/store', { source: 'legacy', view: 'installed' }],
    ['/agentos-console?runId=run_1&source=legacy', '/history', { runId: 'run_1', source: 'legacy', tab: 'acg' }],
  ])('resolves %s to its integrated tab target', async (legacyUrl, targetPath, query) => {
    await router.push(legacyUrl)

    expect(router.currentRoute.value.path).toBe(targetPath)
    expect(router.currentRoute.value.query).toMatchObject(query)
  })
})
