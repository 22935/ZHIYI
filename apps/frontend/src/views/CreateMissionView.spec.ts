import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { workflowApi } from '@/services/api/workflow'
import CreateMissionView from './CreateMissionView.vue'

vi.mock('@/services/api/workflow', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/api/workflow')>()
  return {
    ...actual,
    workflowApi: {
      ...actual.workflowApi,
      createMaterial: vi.fn(),
      uploadAttachment: vi.fn(),
      deleteAttachment: vi.fn(),
      startWorkflowAsync: vi.fn(),
      reconcileMissionLaunch: vi.fn()
    }
  }
})

const workbenchLayoutStub = {
  template: '<section class="workbench-layout-stub"><slot name="main" /></section>'
}

describe('CreateMissionView', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'NOT_FOUND' })
  })
  afterEach(() => vi.resetAllMocks())

  it('retries creation with the same request identity and complete semantic payload', async () => {
    vi.mocked(workflowApi.createMaterial).mockResolvedValue({ manifestId: 'sealed_material' } as any)
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(new Error('lost response')).mockResolvedValueOnce({
      missionId: 'mission_recovered', runId: 'run_recovered', status: 'pending'
    } as any)
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/new', name: 'CreateMission', component: CreateMissionView },
      { path: '/missions/:missionId', name: 'MissionWorkspace', component: { template: '<div />' } }
    ] })
    await router.push('/new')
    await router.isReady()
    const wrapper = mount(CreateMissionView, { global: { plugins: [router], stubs: { WorkbenchLayout: workbenchLayoutStub, PluginExtensionHost: true } } })
    await wrapper.find('#mission-goal').setValue('明确的新目标')
    ;(wrapper.vm as any).draft.materialText = '不可重复创建的材料'
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const first = vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0]
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[1][0]).toEqual(first)
    expect(first.semantics?.objective).toBe('明确的新目标')
    expect(first.clientRequestId).toBeTruthy()
    expect(first.materialRefs).toEqual(['sealed_material'])
    expect(first.input).not.toHaveProperty('materialText')
    expect(workflowApi.createMaterial).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.params.missionId).toBe('mission_recovered')
    wrapper.unmount()
  })

  it('does not create another Mission when the Composer is submitted twice while acceptance is pending', async () => {
    let accept: (value: any) => void
    vi.mocked(workflowApi.startWorkflowAsync).mockImplementation(() => new Promise(resolve => { accept = resolve }))
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/new', name: 'CreateMission', component: CreateMissionView },
      { path: '/missions/:missionId', name: 'MissionWorkspace', component: { template: '<div />' } }
    ] })
    await router.push('/new'); await router.isReady()
    const wrapper = mount(CreateMissionView, { global: { plugins: [router], stubs: { WorkbenchLayout: workbenchLayoutStub, PluginExtensionHost: true } } })
    await wrapper.find('#mission-goal').setValue('唯一启动意图')
    await wrapper.find('form').trigger('submit')
    await wrapper.find('form').trigger('submit')
    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledTimes(1)
    accept!({ missionId: 'mission_unique', runId: 'run_unique', status: 'pending' })
    await flushPromises()
    expect(router.currentRoute.value.params.missionId).toBe('mission_unique')
    wrapper.unmount()
  })

  it('restores an unknown submission after unmount and reuses its Material and exact wire snapshot', async () => {
    vi.mocked(workflowApi.createMaterial).mockResolvedValue({ manifestId: 'original-material' } as any)
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(new Error('lost acceptance')).mockResolvedValueOnce({ missionId: 'restored-mission', runId: 'restored-run', status: 'pending' } as any)
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/new', name: 'CreateMission', component: CreateMissionView },
      { path: '/missions/:missionId', name: 'MissionWorkspace', component: { template: '<div />' } }
    ] })
    await router.push('/new'); await router.isReady()
    const options = { global: { plugins: [router], stubs: { WorkbenchLayout: workbenchLayoutStub, PluginExtensionHost: true } } }
    const first = mount(CreateMissionView, options)
    await first.find('#mission-goal').setValue('恢复原始提交')
    ;(first.vm as any).draft.materialText = '必须复用的材料'
    await first.find('form').trigger('submit'); await flushPromises()
    const original = vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0]
    first.unmount()
    const restored = mount(CreateMissionView, options)
    expect((restored.find('#mission-goal').element as HTMLTextAreaElement).value).toBe('恢复原始提交')
    await restored.findAll('button').find(button => button.text() === '核对并恢复原提交')!.trigger('click')
    await flushPromises()
    expect(workflowApi.reconcileMissionLaunch).toHaveBeenCalledWith(original, undefined)
    expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[1][0]).toEqual(original)
    expect(workflowApi.createMaterial).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.params.missionId).toBe('restored-mission')
    restored.unmount()
  })

  it('renders the mission launcher arrangement and restores runtime settings', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/agentos/missions/new', name: 'CreateMission', component: CreateMissionView },
        { path: '/agentos/acg', name: 'AcgVisualization', component: { template: '<div />' } }
      ]
    })
    await router.push({ name: 'CreateMission' })
    await router.isReady()
    const wrapper = mount(CreateMissionView, {
      global: {
        plugins: [router],
        stubs: { WorkbenchLayout: workbenchLayoutStub, PluginExtensionHost: true }
      }
    })

    expect(wrapper.find('#mission-title').exists()).toBe(false)
    expect(wrapper.find('#mission-files').exists()).toBe(true)
    expect(wrapper.find('#mission-goal').exists()).toBe(true)
    expect(wrapper.text()).toContain('Execution')
    expect(wrapper.text()).toContain('高级运行设置')
    expect(wrapper.find('.create-mission__submit').text()).toContain('创建并运行')
    expect(wrapper.find('.create-mission__back').text()).toContain('返回项目')
    expect(wrapper.find('.create-mission__workspace').exists()).toBe(true)
    expect(wrapper.find('.launch-bar').exists()).toBe(true)
    await wrapper.findAll('button').find(button => button.text() === '人工审核')!.trigger('click')
    expect(wrapper.text()).toContain('每个执行步骤完成后暂停，等待人工审核；最终交付须经批准。')
    wrapper.unmount()
  })

  it('derives a launch summary and keeps Create & Run disabled until the brief is ready', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/agentos/missions/new', name: 'CreateMission', component: CreateMissionView },
        { path: '/agentos/acg', name: 'AcgVisualization', component: { template: '<div />' } }
      ]
    })
    await router.push({ name: 'CreateMission' })
    await router.isReady()
    const wrapper = mount(CreateMissionView, {
      global: {
        plugins: [router],
        stubs: { WorkbenchLayout: workbenchLayoutStub, PluginExtensionHost: true }
      }
    })

    expect(wrapper.find('.context-empty').exists()).toBe(true)
    expect(wrapper.find('.execution-settings').exists()).toBe(true)
    expect(wrapper.findAll('.execution-settings .config-option').length).toBeGreaterThan(0)
    expect(wrapper.find('.create-mission__submit').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.launch-bar__summary').text()).toContain('Dynamic · Native Core')

    await wrapper.find('#mission-goal').setValue('验证 Mission brief 可以启动 Run')
    expect(wrapper.find('.create-mission__submit').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('returns to the project list without retaining the create route', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/agentos/missions/new', name: 'CreateMission', component: CreateMissionView },
        { path: '/agentos/acg', name: 'AcgVisualization', component: { template: '<div />' } }
      ]
    })
    await router.push({ name: 'CreateMission' })
    await router.isReady()
    const wrapper = mount(CreateMissionView, {
      global: {
        plugins: [router],
        stubs: { WorkbenchLayout: workbenchLayoutStub, PluginExtensionHost: true }
      }
    })

    await wrapper.find('.create-mission__back').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.name).toBe('AcgVisualization')
    expect(router.currentRoute.value.query).toEqual({})
    wrapper.unmount()
  })

  it('renders reasoning_effort choices from server capability metadata', async () => {
    localStorage.setItem('kinlin.model_settings', JSON.stringify({
      provider: 'glm',
      apiKey: '',
      baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
      models: ['glm-5.3-flash'],
      selectedModel: 'glm-5.3-flash',
      thinkingMode: 'deep',
      reasoningEffort: 'high'
    }))
    // 档位选择器由服务端能力元数据驱动（/ai/chat/model-capabilities）。
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/ai/chat/model-capabilities')) {
        return new Response(JSON.stringify({
          thinkingModes: ['standard', 'deep'],
          alwaysThinking: true,
          supportsReasoningEffort: true,
          reasoningEfforts: ['low', 'high', 'max'],
          contextWindow: 1048576
        }), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }
      return new Response('{}', { status: 200 })
    }))
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/agentos/missions/new', name: 'CreateMission', component: CreateMissionView },
        { path: '/agentos/acg', name: 'AcgVisualization', component: { template: '<div />' } }
      ]
    })
    await router.push({ name: 'CreateMission' })
    await router.isReady()
    const wrapper = mount(CreateMissionView, {
      global: {
        plugins: [router],
        stubs: { WorkbenchLayout: workbenchLayoutStub, PluginExtensionHost: true }
      }
    })
    await flushPromises()

    const select = wrapper.find('select[aria-label="Thinking strength"]')
    expect(select.findAll('option').map(option => option.attributes('value'))).toEqual(['low', 'high', 'max'])
    expect((select.element as HTMLSelectElement).value).toBe('high')
    await select.setValue('low')
    expect((select.element as HTMLSelectElement).value).toBe('low')

    wrapper.unmount()
    localStorage.removeItem('kinlin.model_settings')
    vi.unstubAllGlobals()
  })

  it('starts a Run with the configured Mission and hands it to Workspace', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockResolvedValue({
      missionId: 'mission_new',
      runId: 'run_new',
      status: 'pending'
    } as any)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/agentos/missions/new', name: 'CreateMission', component: CreateMissionView },
        { path: '/agentos/acg', name: 'AcgVisualization', component: { template: '<div />' } },
        { path: '/agentos/missions/:missionId/workspace', name: 'MissionWorkspace', component: { template: '<div />' } }
      ]
    })
    await router.push({ name: 'CreateMission' })
    await router.isReady()
    const wrapper = mount(CreateMissionView, {
      global: {
        plugins: [router],
        stubs: { WorkbenchLayout: workbenchLayoutStub, PluginExtensionHost: true }
      }
    })

    await wrapper.find('#mission-goal').setValue('输出可验收的实施方案')
    await wrapper.findAll('.config-option').find(button => button.text().includes('Template preferred'))?.trigger('click')
    await wrapper.find('select[aria-label="Planning diversity"]').setValue('exploratory')
    await wrapper.find('input[type="number"]').setValue('42')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        title: '输出可验收的实施方案',
        semantics: { objective: '输出可验收的实施方案', constraints: [], sourceRefs: [] },
        input: expect.objectContaining({
          taskGoal: '输出可验收的实施方案',
          planningMode: 'template_preferred',
          planningDiversity: 'exploratory',
          planningSeed: 42,
          usePlanner: true,
        })
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(router.currentRoute.value.name).toBe('MissionWorkspace')
    expect(router.currentRoute.value.params.missionId).toBe('mission_new')
    expect(router.currentRoute.value.query.runId).toBe('run_new')
    wrapper.unmount()
  })

  it('uploads files first and submits only READY attachment identities', async () => {
    vi.mocked(workflowApi.uploadAttachment).mockResolvedValue({
        attachmentId: 'att_contract', originalFilename: 'contract.txt', filename: 'contract.txt',
        mimeType: 'text/plain', extension: '.txt', sizeBytes: 18, sha256: 'a'.repeat(64),
        status: 'READY', characterCount: 18, parser: 'plain-text:utf-8-sig', metadata: {},
        createdAt: '2026-09-12T00:00:00Z', updatedAt: '2026-09-12T00:00:00Z'
    })
    vi.mocked(workflowApi.startWorkflowAsync).mockResolvedValue({
      missionId: 'mission_attachment', runId: 'run_attachment', status: 'pending'
    } as any)
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/agentos/missions/new', name: 'CreateMission', component: CreateMissionView },
        { path: '/agentos/acg', name: 'AcgVisualization', component: { template: '<div />' } },
        { path: '/agentos/missions/:missionId/workspace', name: 'MissionWorkspace', component: { template: '<div />' } }
      ]
    })
    await router.push({ name: 'CreateMission' })
    await router.isReady()
    const wrapper = mount(CreateMissionView, {
      global: { plugins: [router], stubs: { WorkbenchLayout: workbenchLayoutStub, PluginExtensionHost: true } }
    })
    const file = new File(['amount is 800000'], 'contract.txt', { type: 'text/plain' })
    const input = wrapper.find('#mission-files')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })
    await input.trigger('change')
    await vi.waitFor(() => expect(workflowApi.uploadAttachment).toHaveBeenCalledWith(file, expect.any(Object)))
    await flushPromises()
    expect(wrapper.text()).toContain('TXT · 16 B')
    expect(wrapper.text()).toContain('✓ 已就绪')
    await wrapper.find('#mission-goal').setValue('生成最终合同审查报告')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledWith(
      expect.objectContaining({ attachmentIds: ['att_contract'] }),
      expect.any(Object)
    )
    expect(workflowApi.deleteAttachment).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
