import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { createPinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AcgVisualizationView from './AcgVisualizationView.vue'
import WorkflowProgressBar from '@/components/agentos/WorkflowProgressBar.vue'
import PluginExtensionHost from '@/features/acg/PluginExtensionHost.vue'
import GenericArtifactPanel from '@/features/acg/GenericArtifactPanel.vue'
import { workflowApi, type AcgView, type WorkflowProgress, type WorkflowRun } from '@/services/api/workflow'
import { fileApi } from '@/services/api/file'

vi.mock('@/services/api/workflow', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api/workflow')>()
  return {
    ...actual,
    workflowApi: {
      ...actual.workflowApi,
      listInstalledPlugins: vi.fn(),
      startWorkflow: vi.fn(),
      startWorkflowAsync: vi.fn(),
      getWorkflowProgress: vi.fn(),
      getRun: vi.fn(),
      getAcgView: vi.fn()
    }
  }
})

vi.mock('@/services/api/file', () => ({
  fileApi: {
    uploadTaskMaterial: vi.fn(),
    deleteTaskMaterial: vi.fn(),
    extractDocumentText: vi.fn()
  }
}))

const makeProgress = (overrides: Partial<WorkflowProgress> = {}): WorkflowProgress => ({
  taskId: 'task_1', runId: 'run_1', workflowId: 'workflow_1', status: 'running',
  phase: 'planning', message: '正在规划任务', percent: null,
  totalSteps: 0, pendingSteps: 0, runningSteps: 0, waitingReviewSteps: 0,
  retryingSteps: 0, failedSteps: 0, completedSteps: 0, cancelledSteps: 0,
  currentStepId: null, activeStepIds: [], recoveryCount: 0,
  startedAt: '2026-07-22T00:00:00Z', updatedAt: '2026-07-22T00:00:01Z',
  progress: 0, percentage: 0,
  ...overrides
})

const makeRun = (): WorkflowRun => ({
  runId: 'run_1', taskId: 'task_1', workflowId: 'native_acg_runtime_v1', domain: 'general',
  status: 'running', reviewMode: 'auto', input: {}, output: {}, steps: [], checkpoints: [], trace: [],
  enabledPluginIds: [], resolvedEnabledPluginIds: [], pluginSnapshot: [], legacyPluginScope: false
})

const makeAcg = (): AcgView => ({
  runId: 'run_1', status: 'running', engine: 'acg', acgBlueprint: null,
  completedStepIds: [], activeStepIds: [], stepStates: [],
  provenance: { productions: [], consumptions: [], interactions: [] }, interactions: [],
  contractViolations: [], recoveryTrace: [], scheduleTrace: [], deliverables: [], finalReport: null,
  lowEntropyMetrics: {
    averageSavingRatio: 0, effectiveSavingRatio: 0, tokensAvailable: 0, tokensDelivered: 0,
    tokensSaved: 0, recoveryCount: 0, interactionCount: 0, contractViolationCount: 0,
    integrityStatus: 'valid'
  }
})

const buttonStub = {
  emits: ['click'],
  template: '<button type="button" @click="$emit(\'click\')"><slot /></button>'
}

const mountPage = async (query = ''): Promise<{ wrapper: VueWrapper; router: Router }> => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/agentos/acg', component: { template: '<div />' } },
      { path: '/agentos-console', component: { template: '<div />' } }
    ]
  })
  await router.push(`/agentos/acg${query}`)
  await router.isReady()
  const wrapper = shallowMount(AcgVisualizationView, {
    global: {
      plugins: [createPinia(), router],
      stubs: {
        'el-button': buttonStub,
        'el-input': true,
        'el-input-number': true,
        'el-icon': true,
        'el-tag': { template: '<span class="el-tag-stub"><slot /></span>' },
        'el-radio-group': true,
        'el-radio-button': true,
        'el-checkbox': true,
        'el-checkbox-group': true,
        'el-checkbox-button': true,
        'el-select': true,
        'el-option': true,
        PluginExtensionHost: false
      }
    }
  })
  await flushPromises()
  return { wrapper, router }
}

const clickStart = async (wrapper: VueWrapper) => {
  const button = wrapper.findAll('button').find((item) => item.text().includes('启动 ACG'))
  if (!button) throw new Error('start button not found')
  await button.trigger('click')
  await flushPromises()
}

describe('AcgVisualizationView async progress loop', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.mocked(workflowApi.startWorkflowAsync).mockResolvedValue({
      accepted: true,
      acgTaskId: 'run_1',
      task: { taskId: 'task_1', status: 'pending' },
      run: { runId: 'run_1', status: 'pending', lifecyclePhase: 'understanding' }
    })
    vi.mocked(workflowApi.listInstalledPlugins).mockResolvedValue([
      {
        pluginId: 'kinlin.legal', version: '0.1.0', displayName: '法律能力包',
        description: '合同审查、证据匹配、风险分析与法律报告能力。', available: true,
        capabilityCount: 7, agentCount: 14, workflowCount: 2, uiExtensionId: 'kinlin.legal'
      },
      {
        pluginId: 'programmer', version: '0.1.0', displayName: 'Programmer Pack',
        description: 'Programmer workflow pack scaffold.', available: true,
        capabilityCount: 0, agentCount: 0, workflowCount: 0, uiExtensionId: null
      }
    ])
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(makeProgress())
    vi.mocked(workflowApi.getRun).mockResolvedValue(makeRun())
    vi.mocked(workflowApi.getAcgView).mockResolvedValue(makeAcg())
    vi.mocked(fileApi.uploadTaskMaterial).mockResolvedValue({
      materialId: 'mat_123', state: 'ready', originalFilename: '合同.txt', mediaType: 'text/plain',
      size: 18, sha256: 'source_hash', extractedTextSha256: 'text_hash', extractedText: '上传后的合同正文',
      textLength: 8, extraction: { method: 'utf-8', ocrUsed: false, pages: 0 }
    })
    vi.mocked(fileApi.deleteTaskMaterial).mockResolvedValue()
  })

  it('uploads generic task material through the task material API and shows the ready state', async () => {
    const { wrapper } = await mountPage()
    const input = wrapper.find('input[type="file"]')
    const file = new File(['上传后的合同正文'], '合同.txt', { type: 'text/plain' })
    Object.defineProperty(input.element, 'files', { configurable: true, value: [file] })

    await input.trigger('change')
    await flushPromises()

    expect(fileApi.uploadTaskMaterial).toHaveBeenCalledWith(file, expect.any(Function))
    expect(wrapper.find('.contract-upload__copy').text()).toContain('合同.txt')
    expect(wrapper.find('.contract-upload__copy').text()).toContain('已提取')
    wrapper.unmount()
  })

  it('surfaces the backend 422 message without discarding the existing draft text', async () => {
    vi.mocked(fileApi.uploadTaskMaterial).mockRejectedValueOnce({
      response: { status: 422, data: { error: 'MATERIAL_FILE_REQUIRED', message: '上传请求缺少 file 字段' } }
    })
    const { wrapper } = await mountPage()
    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [new File(['probe'], '合同.txt', { type: 'text/plain' })]
    })

    await input.trigger('change')
    await flushPromises()

    expect(wrapper.find('.contract-upload__error').text()).toBe('上传请求缺少 file 字段')
    wrapper.unmount()
  })

  afterEach(() => {
    vi.clearAllMocks()
    vi.useRealTimers()
  })

  it('uses the fixed ACG engine header and routes to history operations', async () => {
    const { wrapper, router } = await mountPage()

    expect(wrapper.find('.hero-left h3').text()).toBe('ACG 动态群体智能引擎')
    expect(wrapper.find('.hero-run-chip').text()).toContain('RUN')
    expect(wrapper.find('.hero-engine').text()).toBe('engine: acg')

    await wrapper.find('.hero-operations').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/agentos-console')
    expect(router.currentRoute.value.query.source).toBe('acg')
    wrapper.unmount()
  })

  it('starts Native explicitly, writes runId to query, and begins progress immediately', async () => {
    const { wrapper, router } = await mountPage()
    await clickStart(wrapper)

    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledOnce()
    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledWith(expect.objectContaining({
      title: '基础软件项目实施方案',
      domain: 'general',
      intent: 'general',
      workflowId: undefined,
      enabledPluginIds: [],
      reviewMode: 'auto',
      input: expect.objectContaining({
        source: 'acg',
        userIntent: '设计一个基础软件项目实施方案，包括目标、阶段、风险和交付物'
      })
    }), expect.any(Object))
    expect(workflowApi.startWorkflow).not.toHaveBeenCalled()
    expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0].clientRequestId).toBeTruthy()
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run_1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(router.currentRoute.value.query.runId).toBe('run_1')
    expect(workflowApi.getAcgView).not.toHaveBeenCalled()
    expect(wrapper.find('.input-panel-expandable').attributes('style') || '').not.toContain('display: none')
    await vi.advanceTimersByTimeAsync(1400)
    expect(wrapper.find('.input-summary').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(450)
    expect(wrapper.find('.input-summary').exists()).toBe(true)
    expect(wrapper.find('.input-panel-expandable').attributes('style')).toContain('display: none')
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(true)
    expect(wrapper.findAll('.plugin-card').every(item => item.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.find('.ctrl-options').exists()).toBe(true)
    expect(wrapper.findAll('.input-panel-toggle')).toHaveLength(1)
    expect(wrapper.find('.input-panel-toggle').attributes('aria-expanded')).toBe('false')
    await wrapper.find('.input-panel-toggle').trigger('click')
    expect(wrapper.find('.input-panel-expandable').attributes('style')).not.toContain('display: none')
    expect(wrapper.find('.input-panel-toggle').attributes('aria-expanded')).toBe('true')
    wrapper.unmount()
  })

  it('removes a locally cached Run when progress returns 404', async () => {
    localStorage.setItem('workflow.run.references.v1', JSON.stringify({
      run_missing: { runId: 'run_missing', source: 'acg', status: 'completed' }
    }))
    vi.mocked(workflowApi.getWorkflowProgress).mockRejectedValue(Object.assign(new Error('missing'), {
      isAxiosError: true,
      response: { status: 404 }
    }))

    const { wrapper, router } = await mountPage('?runId=run_missing')
    await flushPromises()

    expect(router.currentRoute.value.query.runId).toBeUndefined()
    expect(JSON.parse(localStorage.getItem('workflow.run.references.v1') || '{}').run_missing).toBeUndefined()
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps the compact header context visible before a Run starts', async () => {
    const { wrapper } = await mountPage()

    expect(wrapper.find('.hero-left').text()).toContain('ACG 动态群体智能引擎')
    expect(wrapper.find('.hero-run-chip').text()).toContain('RUN—')
    expect(wrapper.find('.hero-right').text()).toContain('准备中')
    expect(wrapper.find('.hero-engine').text()).toBe('engine: acg')
    expect(wrapper.find('.hero-icon-action').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.task-brief').text()).toBe('ACG 动态智能体长程任务')
    expect(wrapper.text()).toContain('知弈OS 原生任务工作台')
    expect(wrapper.text()).toContain('任务材料')
    expect(wrapper.text()).not.toContain('合同文本')
    expect(wrapper.text()).not.toContain('法律风险')
    expect(wrapper.text()).not.toContain('甲方')
    expect(wrapper.text()).not.toContain('乙方')
    expect(wrapper.find('#acg-task-name').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('测试预设')
    wrapper.unmount()
  })

  it('adds the Legal extension to the same workbench and sends an explicit plugin scope', async () => {
    const { wrapper } = await mountPage()
    const legalCard = wrapper.findAll('.plugin-card').find(item => item.text().includes('法律能力包'))
    expect(legalCard).toBeTruthy()
    await legalCard!.trigger('click')
    expect(wrapper.findComponent(PluginExtensionHost).props('extensions'))
      .toEqual([expect.objectContaining({ pluginId: 'kinlin.legal' })])

    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      configurable: true,
      value: [new File(['上传后的合同正文'], '合同.txt', { type: 'text/plain' })]
    })
    await input.trigger('change')
    await flushPromises()
    await clickStart(wrapper)

    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledWith(expect.objectContaining({
      title: '识别合同风险、核验法律依据并生成修改建议',
      domain: 'legal',
      intent: 'contract_review',
      enabledPluginIds: ['kinlin.legal'],
      reviewMode: 'human_in_loop',
      input: expect.objectContaining({
        userIntent: '识别合同风险、核验法律依据并生成修改建议',
        contractText: '上传后的合同正文',
        evidenceFirst: true,
        riskParallel: true,
        conservativeReview: true
      })
    }), expect.any(Object))
    wrapper.unmount()
  })

  it('keeps Native enabled and replaces the selected professional pack', async () => {
    const { wrapper } = await mountPage()
    const pluginCards = wrapper.findAll('.plugin-card')
    const nativeCard = pluginCards.find(item => item.text().includes('Native Core'))
    const legalCard = pluginCards.find(item => item.text().includes('法律能力包'))
    const programmerCard = pluginCards.find(item => item.text().includes('Programmer Pack'))

    expect(nativeCard?.attributes('aria-pressed')).toBe('true')
    await legalCard!.trigger('click')
    expect(legalCard?.attributes('aria-pressed')).toBe('true')
    expect(wrapper.findComponent(PluginExtensionHost).props('extensions'))
      .toEqual([expect.objectContaining({ pluginId: 'kinlin.legal' })])

    await programmerCard!.trigger('click')
    expect(legalCard?.attributes('aria-pressed')).toBe('false')
    expect(programmerCard?.attributes('aria-pressed')).toBe('true')
    expect(nativeCard?.text()).toContain('作为专业能力包的运行基础')
    expect(wrapper.findComponent(PluginExtensionHost).props('extensions')).toEqual([])

    await clickStart(wrapper)
    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledWith(expect.objectContaining({
      title: '设计一个基础软件项目实施方案，包括目标、阶段、风险和交付物',
      domain: 'general',
      intent: 'general',
      enabledPluginIds: ['programmer'],
      reviewMode: 'auto'
    }), expect.any(Object))
    wrapper.unmount()
  })

  it('locks plugin selection to the historical Run snapshot and reports a missing plugin', async () => {
    vi.mocked(workflowApi.listInstalledPlugins).mockResolvedValueOnce([])
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(makeProgress({
      phase: 'executing', status: 'running'
    }))
    vi.mocked(workflowApi.getRun).mockResolvedValue({
      ...makeRun(), domain: 'legal', workflowId: 'legal_contract_review_v1',
      enabledPluginIds: ['kinlin.legal'], resolvedEnabledPluginIds: ['kinlin.legal'],
      pluginSnapshot: [{
        pluginId: 'kinlin.legal', version: '0.1.0', manifestHash: 'manifest',
        contributionRevision: 'contribution'
      }], capabilityCatalogRevision: 'catalog-revision'
    })

    const { wrapper } = await mountPage('?runId=run_1')
    await vi.advanceTimersByTimeAsync(0)
    await flushPromises()

    expect(wrapper.find('.run-scope').text()).toContain('本次 Run 的能力范围（已冻结）')
    expect(wrapper.find('.run-scope').text()).toContain('kinlin.legal')
    expect(wrapper.find('.scope-warning').text()).toContain('原插件当前不可用')
    expect(wrapper.findAll('.plugin-card').every(item => item.attributes('disabled') !== undefined)).toBe(true)
    wrapper.unmount()
  })

  it('labels legacy history without inventing a plugin version', async () => {
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(makeProgress({
      phase: 'executing', status: 'running'
    }))
    vi.mocked(workflowApi.getRun).mockResolvedValue({ ...makeRun(), legacyPluginScope: true })

    const { wrapper } = await mountPage('?runId=run_1')
    await vi.advanceTimersByTimeAsync(0)
    await flushPromises()

    expect(wrapper.find('.scope-warning').text()).toContain('插件快照功能之前')
    expect(wrapper.find('.snapshot-list').text()).toContain('Native only')
    wrapper.unmount()
  })

  it('restores a query runId without starting a duplicate workflow', async () => {
    const { wrapper } = await mountPage('?runId=run_1')

    expect(workflowApi.startWorkflowAsync).not.toHaveBeenCalled()
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run_1', expect.any(Object))
    expect(workflowApi.getAcgView).not.toHaveBeenCalled()
    expect(wrapper.find('.input-summary').exists()).toBe(true)
    expect(wrapper.find('.ctrl-options').exists()).toBe(true)
    wrapper.unmount()
  })

  it('does not load topology in planning but loads it when execution begins', async () => {
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(makeProgress({
      phase: 'executing', percent: 25, totalSteps: 4, completedSteps: 1, updatedAt: '2026-07-22T00:00:02Z'
    }))
    const { wrapper } = await mountPage('?runId=run_1')
    await vi.advanceTimersByTimeAsync(0)
    await flushPromises()

    expect(workflowApi.getAcgView).toHaveBeenCalledOnce()
    expect(workflowApi.getRun).toHaveBeenCalledOnce()
    expect(wrapper.findComponent(GenericArtifactPanel).exists()).toBe(true)
    wrapper.unmount()
  })

  it('refreshes Run Detail and ACG immediately when graphVersion changes', async () => {
    vi.mocked(workflowApi.getWorkflowProgress)
      .mockResolvedValueOnce(makeProgress({
        phase: 'executing', graphVersion: 1, percent: 25, totalSteps: 4, completedSteps: 1
      }))
      .mockResolvedValueOnce(makeProgress({
        phase: 'executing', graphVersion: 2, dynamicStepCount: 2,
        percent: 16.67, totalSteps: 6, completedSteps: 1, updatedAt: '2026-07-22T00:00:02Z'
      }))
    const { wrapper } = await mountPage('?runId=run_1')
    await vi.advanceTimersByTimeAsync(0)
    await flushPromises()
    expect(workflowApi.getAcgView).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(workflowApi.getAcgView).toHaveBeenCalledTimes(2)
    expect(workflowApi.getRun).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('forces final ACG loading for completed and keeps review polling nonterminal', async () => {
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValueOnce(makeProgress({
      phase: 'review', status: 'waiting_review', percent: 75
    })).mockResolvedValueOnce(makeProgress({
      phase: 'completed', status: 'completed', percent: 100, completedSteps: 4, totalSteps: 4
    }))
    const { wrapper } = await mountPage('?runId=run_1')

    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledTimes(2)
    expect(workflowApi.getAcgView).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('reconciles a stale terminal ACG view with the final artifact stored on the Run', async () => {
    const finalArtifact = {
      artifactId: 'artifact_final', type: 'report', title: '最终实施方案',
      mediaType: 'text/markdown', content: '完整成果',
      structuredData: { title: '最终实施方案', sections: [] }
    }
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(makeProgress({
      phase: 'completed', status: 'completed', percent: 100,
      completedSteps: 1, totalSteps: 1
    }))
    vi.mocked(workflowApi.getRun).mockResolvedValue({
      ...makeRun(), status: 'completed', output: { final_answer: '完整成果' },
      steps: [{
        stepId: 'deliver', name: '成果生成', agentName: 'native_general_agent',
        status: 'completed', output: { artifact: finalArtifact, final_answer: '完整成果' }
      }]
    })
    vi.mocked(workflowApi.getAcgView).mockResolvedValue({
      ...makeAcg(), status: 'completed', stepOutputs: [], finalArtifacts: [], finalReport: null
    })

    const { wrapper } = await mountPage('?runId=run_1')
    await flushPromises()

    const panel = wrapper.findComponent(GenericArtifactPanel)
    expect(panel.props('finalArtifacts')).toEqual([{ ...finalArtifact, stepId: 'deliver' }])
    expect(panel.props('stepOutputs')).toEqual([{
      stepId: 'deliver', name: '成果生成', status: 'completed',
      output: { artifact: finalArtifact, final_answer: '完整成果' }
    }])
    expect(panel.props('status')).toBe('completed')
    wrapper.unmount()
  })

  it('keeps the completed ACG delivery visible when Run detail loading fails', async () => {
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(makeProgress({
      phase: 'completed', status: 'completed', percent: 100,
      completedSteps: 1, totalSteps: 1
    }))
    vi.mocked(workflowApi.getRun).mockRejectedValue({
      response: { status: 502 }
    })
    vi.mocked(workflowApi.getAcgView).mockResolvedValue({
      ...makeAcg(),
      status: 'completed',
      stepOutputs: [{ stepId: 'delivery', name: '交付', status: 'completed', output: { result: 'done' } }],
      finalArtifacts: [{
        artifactId: 'artifact_delivery',
        type: 'implementation_plan',
        title: '完整实施方案',
        mediaType: 'text/markdown',
        content: '# 完整实施方案',
        structuredData: { executiveSummary: '可直接阅读的交付摘要' },
        stepId: 'delivery'
      }]
    })

    const { wrapper } = await mountPage('?runId=run_1')
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()

    const panel = wrapper.findComponent(GenericArtifactPanel)
    expect(panel.exists()).toBe(true)
    expect(panel.props('finalArtifacts')).toHaveLength(1)
    expect(panel.props('stepOutputs')).toHaveLength(1)
    expect(panel.props('status')).toBe('completed')
    wrapper.unmount()
  })

  it('shows the review panel when the canonical Run is waiting even if progress is briefly stale', async () => {
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(makeProgress({
      phase: 'executing', status: 'running', percent: 75, waitingReviewSteps: 0,
      currentStepId: 'human_review', activeStepIds: ['human_review']
    }))
    vi.mocked(workflowApi.getRun).mockResolvedValue({
      ...makeRun(), status: 'waiting_review',
      steps: [{ stepId: 'human_review', name: '人工审核', agentName: 'reviewer', status: 'waiting_review' }]
    })
    const { wrapper } = await mountPage('?runId=run_1')
    await vi.advanceTimersByTimeAsync(0)
    await flushPromises()

    expect(wrapper.findComponent({ name: 'WorkflowReviewPanel' }).exists()).toBe(true)
    wrapper.unmount()
  })

  it('shows idempotency conflict separately from a workflow failure', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValue({
      isAxiosError: true,
      response: { status: 409 }
    })
    const { wrapper } = await mountPage()
    await clickStart(wrapper)

    expect(wrapper.text()).toContain('相同请求标识已用于不同参数')
    expect(wrapper.text()).not.toContain('工作流执行失败')
    wrapper.unmount()
  })

  it('shows a safe backend contract error instead of hiding it behind a generic start failure', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValue({
      isAxiosError: true,
      response: {
        status: 400,
        data: {
          message: '请求参数格式错误',
          error: '请求中包含未知字段，请检查请求参数'
        }
      }
    })
    const { wrapper } = await mountPage()
    await clickStart(wrapper)

    expect(wrapper.text()).toContain('任务未能启动：请求参数格式错误：请求中包含未知字段，请检查请求参数')
    wrapper.unmount()
  })

  it('aborts an outstanding start request when the page unmounts', async () => {
    let signal: AbortSignal | undefined
    vi.mocked(workflowApi.startWorkflowAsync).mockImplementation((_payload, options) => {
      signal = options.signal
      return new Promise(() => undefined)
    })
    const { wrapper } = await mountPage()
    const startPromise = clickStart(wrapper)
    await Promise.resolve()
    wrapper.unmount()
    expect(signal?.aborted).toBe(true)
    void startPromise
  })

  it('completes the controlled T0-T6 lifecycle without polling full ACG every two seconds', async () => {
    vi.mocked(workflowApi.getWorkflowProgress)
      .mockResolvedValueOnce(makeProgress({ phase: 'understanding', message: '理解任务' }))
      .mockResolvedValueOnce(makeProgress({ phase: 'planning', message: '规划任务', updatedAt: '2026-07-22T00:00:02Z' }))
      .mockResolvedValueOnce(makeProgress({ phase: 'graph_building', message: '构建 ACG', updatedAt: '2026-07-22T00:00:03Z' }))
      .mockResolvedValueOnce(makeProgress({
        phase: 'executing', message: '执行节点', percent: 50, totalSteps: 4, completedSteps: 2,
        updatedAt: '2026-07-22T00:00:04Z'
      }))
      .mockResolvedValueOnce(makeProgress({
        phase: 'completed', status: 'completed', message: '执行完成', percent: 100,
        totalSteps: 4, completedSteps: 4, updatedAt: '2026-07-22T00:00:05Z'
      }))
    const { wrapper } = await mountPage()
    await clickStart(wrapper)

    for (let second = 2; second <= 8; second += 2) {
      await vi.advanceTimersByTimeAsync(2000)
      await flushPromises()
    }

    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledTimes(5)
    expect(workflowApi.getAcgView).toHaveBeenCalledTimes(2)
    expect(workflowApi.getRun).toHaveBeenCalledTimes(2)
    expect(vi.mocked(workflowApi.getAcgView).mock.calls.every(([runId]) => runId === 'run_1')).toBe(true)
    wrapper.unmount()
  })
})
