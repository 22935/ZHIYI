import { beforeEach, describe, expect, it, vi } from 'vitest'
import router from './index'
vi.mock('@/views/ChatView.vue', () => ({ default: { template: '<main>Chat</main>' } }))
vi.mock('@/views/HistoryView.vue', () => ({ default: { template: '<main>History</main>' } }))
vi.mock('@/views/ResourceCenterView.vue', () => ({ default: { template: '<main>Resources</main>' } }))

describe('local application routing', () => {
  beforeEach(() => { localStorage.clear() })
  it('opens chat directly without account credentials', async () => {
    await router.push('/')
    expect(router.currentRoute.value.path).toBe('/chat')
    expect(localStorage.getItem('token')).toBeNull()
  })
  it('resolves an old login bookmark to the application', async () => {
    await router.push('/login')
    expect(router.currentRoute.value.path).toBe('/chat')
  })
  it('allows a workspace route without token verification', async () => {
    await router.push('/history?tab=acg')
    expect(router.currentRoute.value.path).toBe('/history')
    expect(router.currentRoute.value.query.tab).toBe('acg')
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
    ['/roles', '/agentos/resources', {}],
    ['/federated-learning', '/agentos/resources', { tab: 'federated' }],
    ['/federated-models', '/agentos/resources', { tab: 'models' }],
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
    ['/roles?source=legacy', '/agentos/resources', { source: 'legacy' }],
    ['/federated-learning?source=legacy', '/agentos/resources', { source: 'legacy', tab: 'federated' }],
    ['/federated-models?source=legacy', '/agentos/resources', { source: 'legacy', tab: 'models' }],
    ['/agentos-console?runId=run_1&source=legacy', '/history', { runId: 'run_1', source: 'legacy', tab: 'acg' }],
  ])('resolves %s to its integrated tab target', async (legacyUrl, targetPath, query) => {

    await router.push(legacyUrl)

    expect(router.currentRoute.value.path).toBe(targetPath)
    expect(router.currentRoute.value.query).toMatchObject(query)
  })
})
