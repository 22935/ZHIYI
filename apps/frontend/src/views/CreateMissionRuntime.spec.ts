import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CreateMissionView from './CreateMissionView.vue'
import { workflowApi } from '@/services/api/workflow'

vi.mock('@/platform', () => ({ platform: { platform: 'web' }, apiUrl: (path: string) => path }))
vi.mock('@/services/api/workflow', async original => {
  const actual = await original<typeof import('@/services/api/workflow')>()
  return { ...actual, workflowApi: { ...actual.workflowApi, startWorkflowAsync: vi.fn() } }
})
let wrapper: VueWrapper | undefined
const page = async (efforts: string[], alwaysThinking = false) => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({
    models: ['test-model'], default_model: 'test-model', capabilities: { 'test-model': {
      thinkingModes: alwaysThinking ? ['standard', 'deep'] : ['disabled', 'standard', 'deep'],
      alwaysThinking, supportsReasoningEffort: true, reasoningEfforts: efforts, defaultReasoningEffort: 'high'
    } }
  }), { status: 200 })))
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/new', name: 'CreateMission', component: CreateMissionView },
    { path: '/missions/:missionId', name: 'MissionWorkspace', component: { template: '<div />' } }
  ] })
  await router.push('/new'); await router.isReady()
  wrapper = mount(CreateMissionView, { global: { plugins: [router], stubs: {
    WorkbenchLayout: { template: '<main><slot name="main" /></main>' }, PluginExtensionHost: true
  } } })
  await flushPromises()
  await wrapper.get('#mission-goal').setValue('验证运行设置')
  return wrapper
}

describe('Create Mission runtime settings', () => {
  beforeEach(() => {
    localStorage.clear(); sessionStorage.clear(); vi.clearAllMocks()
    localStorage.setItem('kinlin.model_settings', JSON.stringify({ provider: 'system', selectedModel: '系统默认',
      models: [], apiKey: '', baseUrl: '', thinkingMode: 'deep', reasoningEffort: 'high' }))
    vi.mocked(workflowApi.startWorkflowAsync).mockResolvedValue({ missionId: 'mission', runId: 'run', status: 'pending' } as any)
  })
  afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('actually submits thinking disabled despite a saved global effort, and omits inert toggles', async () => {
    const view = await page(['low', 'high', 'max'])
    const selection = view.get('select[aria-label="Thinking strength"]')
    await selection.setValue('disabled')
    expect((selection.element as HTMLSelectElement).value).toBe('disabled')
    await view.get('form').trigger('submit'); await flushPromises()
    const input = vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0].input
    expect(input).toMatchObject({ thinkingMode: 'disabled' })
    expect(input?.reasoningEffort).toBeUndefined()
    expect(input).not.toHaveProperty('debugTrace')
    expect(input).not.toHaveProperty('lowEntropyOptions')
  })

  it('uses the lowest supported fast preset and marks a changed profile as custom', async () => {
    const view = await page(['medium', 'high'], true)
    const fast = view.findAll('button').find(button => button.text() === '快速')!
    await fast.trigger('click')
    expect((view.get('select[aria-label="Thinking strength"]').element as HTMLSelectElement).value).toBe('medium')
    expect(fast.classes()).toContain('is-selected')
    await view.get('select[aria-label="Capability profile"]').setValue('full')
    expect(fast.classes()).not.toContain('is-selected')
  })

  it('blocks fractional seeds and accepts the backend safe-integer limit', async () => {
    const view = await page(['low', 'high', 'max'])
    const seed = view.get('input[aria-label="Planning seed"]')
    await seed.setValue('1.5')
    expect(view.get('.create-mission__submit').attributes('disabled')).toBeDefined()
    await view.get('form').trigger('submit'); await flushPromises()
    expect(workflowApi.startWorkflowAsync).not.toHaveBeenCalled()
    await seed.setValue('9007199254740991')
    expect(view.get('.create-mission__submit').attributes('disabled')).toBeUndefined()
    await view.get('form').trigger('submit'); await flushPromises()
    expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0].input?.planningSeed).toBe(9007199254740991)
  })
})
