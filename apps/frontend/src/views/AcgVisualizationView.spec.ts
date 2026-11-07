import { createPinia, setActivePinia } from 'pinia'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  workflowApi,
  type AcgView,
  type WorkflowProgress,
  type WorkflowRun
} from '@/services/api/workflow'
import WorkflowProgressBar from '@/components/agentos/WorkflowProgressBar.vue'
import AgentOsRunSummaryCard from '@/components/agentos/AgentOsRunSummaryCard.vue'
import AcgVisualizationView from './AcgVisualizationView.vue'
import { chooseFailedRunRetryMode } from '@/utils/retryModeChoice'
import { createMissionLaunchAttempt } from '@/features/mission/launchAttempt'
import { legacyAcgLaunchCommand } from '@/features/mission/command'
import { createNativeWorkbenchDraft } from '@/features/acg/workbench'

vi.mock('@/utils/retryModeChoice', () => ({
  chooseFailedRunRetryMode: vi.fn().mockResolvedValue('successor_run')
}))

vi.mock('@/services/api/workflow', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/api/workflow')>()
  return {
    ...actual,
    workflowApi: {
      ...actual.workflowApi,
      startWorkflowAsync: vi.fn(),
      reconcileMissionLaunch: vi.fn(),
      rerunWorkflowAsync: vi.fn(),
      retryWorkflowStepAsync: vi.fn(),
      getWorkflowProgress: vi.fn(),
      getRun: vi.fn(),
      getRunHistoryConfig: vi.fn(),
      getRunResourceUsage: vi.fn(),
      getAcgView: vi.fn()
    }
  }
})

const progress = (overrides: Partial<WorkflowProgress> = {}): WorkflowProgress => ({
  missionId: 'mission_1', runId: 'run_1', workflowId: 'native_acg_runtime_v1', status: 'running',
  phase: 'executing', message: '正在执行节点', percent: 50, totalSteps: 4, pendingSteps: 1,
  runningSteps: 1, waitingReviewSteps: 0, retryingSteps: 0, failedSteps: 0,
  completedSteps: 2, cancelledSteps: 0, currentStepId: 'step_3', activeStepIds: ['step_3'],
  recoveryCount: 0, startedAt: '2026-08-20T00:00:00Z', updatedAt: '2026-08-20T00:01:00Z',
  progress: 0.5, percentage: 50, ...overrides
})

const run = (overrides: Partial<WorkflowRun> = {}): WorkflowRun => ({
  runId: 'run_1', missionId: 'mission_1', workflowId: 'native_acg_runtime_v1', domain: 'general',
  title: '测试 ACG 任务', status: 'running', steps: [], activeStepIds: ['step_3'],
  lifecyclePhase: 'executing', lifecycleMessage: '正在执行节点', ...overrides
})

const acg = (overrides: Partial<AcgView> = {}): AcgView => ({
  runId: 'run_1', status: 'running', engine: 'acg', acgBlueprint: null, graphVersion: 1,
  completedStepIds: [], activeStepIds: ['step_3'], stepStates: [],
  provenance: { productions: [], consumptions: [], interactions: [] }, interactions: [],
  contractViolations: [], recoveryTrace: [], scheduleTrace: [], deliverables: [], finalReport: null,
  lowEntropyMetrics: { averageSavingRatio: 0, effectiveSavingRatio: 0, tokensAvailable: 0,
    tokensDelivered: 0, tokensSaved: 0, recoveryCount: 0, interactionCount: 0,
    contractViolationCount: 0, integrityStatus: 'valid' },
  ...overrides
})

const buttonStub = {
  emits: ['click'],
  template: '<button type="button" @click="$emit(\'click\')"><slot /></button>'
}

const workbenchLayoutStub = {
  props: ['showRight'],
  template: `
    <section class="workbench-layout-stub">
      <slot name="left" />
      <slot
        name="main"
        :left-collapsed-by-user="false"
        :right-collapsed-by-user="false"
        :left-auto-hidden="false"
        :right-auto-hidden="false"
        :right-enabled="showRight"
        :toggle-left="noop"
        :toggle-right="noop"
      />
      <slot name="right" />
    </section>
  `,
  methods: {
    noop() {}
  }
}

const workbenchBottomPanelStub = {
  props: ['modelValue', 'collapsed', 'tabs'],
  emits: ['update:modelValue', 'update:collapsed'],
  template: `
    <section class="workbench-bottom-panel-stub">
      <slot name="tab-result" />
      <slot name="tab-trace" />
      <slot name="tab-events" />
      <slot name="tab-tools" />
    </section>
  `
}

const workbenchVerticalSplitStub = {
  template: `
    <section class="workbench-vertical-split-stub">
      <slot name="graph" />
      <slot name="bottom" :collapsed="false" :set-collapsed="noop" :toggle-collapsed="noop" />
    </section>
  `,
  methods: {
    noop() {}
  }
}

const mountPage = async (query = ''): Promise<{ wrapper: VueWrapper; router: Router }> => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/agentos/acg', component: { template: '<div />' } },
      { path: '/history', component: { template: '<div />' } }
    ]
  })
  await router.push(`/agentos/acg${query}`)
  await router.isReady()
  const pinia = createPinia()
  setActivePinia(pinia)
  const wrapper = shallowMount(AcgVisualizationView, {
    global: {
      plugins: [pinia, router],
      stubs: {
        'el-button': buttonStub,
        'el-icon': true,
        'el-input': true,
        'el-input-number': true,
        'el-tag': { template: '<span><slot /></span>' },
        'el-drawer': {
          props: ['modelValue'],
          emits: ['update:modelValue'],
          template: '<div v-if="modelValue"><slot name="header" /><slot /></div>'
        },
        'el-radio-group': true,
        'el-radio-button': true,
        'el-switch': true,
        'el-checkbox': true,
        'el-checkbox-group': true,
        'el-select': true,
        'el-option': true,
        WorkbenchLayout: workbenchLayoutStub,
        WorkbenchBottomPanel: workbenchBottomPanelStub,
        WorkbenchVerticalSplit: workbenchVerticalSplitStub
      }
    }
  })
  await flushPromises()
  return { wrapper, router }
}

describe('AcgVisualizationView 执行运行时 page wiring', () => {
  beforeEach(() => {
    localStorage.clear(); localStorage.setItem('userId', 'local-owner')
    sessionStorage.clear()
    vi.clearAllMocks()
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress())
    vi.mocked(workflowApi.getRun).mockResolvedValue(run())
    vi.mocked(workflowApi.getAcgView).mockResolvedValue(acg())
    vi.mocked(workflowApi.getRunHistoryConfig).mockResolvedValue({
      runId: 'run_1', title: '测试 ACG 任务', reviewMode: 'auto', enabledPluginIds: [], input: {}
    })
    vi.mocked(workflowApi.getRunResourceUsage).mockResolvedValue(null as never)
    vi.mocked(workflowApi.startWorkflowAsync).mockResolvedValue(run({ status: 'pending', lifecyclePhase: 'planning' }))
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'NOT_FOUND' })
    vi.mocked(workflowApi.rerunWorkflowAsync).mockResolvedValue(run({
      runId: 'run_2', missionId: 'mission_1', status: 'pending', lifecyclePhase: 'planning'
    }))
    vi.mocked(workflowApi.retryWorkflowStepAsync).mockResolvedValue(run({
      runId: 'run_2', missionId: 'mission_1', status: 'pending', lifecyclePhase: 'executing'
    }))
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('renders the native workbench without inventing a Run before submission', async () => {
    const { wrapper } = await mountPage()

    expect(wrapper.find('.hero-left').text()).toContain('ACG 动态群体智能引擎')
    expect(wrapper.find('.hero-run-chip').exists()).toBe(false)
    expect(wrapper.text()).toContain('任务定义')
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(false)
    expect(workflowApi.getWorkflowProgress).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('opens advanced run settings as a downward popover without changing the primary controls', async () => {
    const { wrapper } = await mountPage()

    expect(wrapper.find('.advanced-settings').exists()).toBe(false)
    await wrapper.find('.advanced-toggle').trigger('click')
    await flushPromises()

    expect(wrapper.find('.advanced-toggle').attributes('aria-expanded')).toBe('true')
    expect(wrapper.find('.primary-options .primary-config').exists()).toBe(true)
    await wrapper.find('.advanced-toggle').trigger('click')
    expect(wrapper.find('.advanced-toggle').attributes('aria-expanded')).toBe('false')
    wrapper.unmount()
  })

  it('restores a URL Run and keeps the progress and 执行运行时 summary visible', async () => {
    const { wrapper } = await mountPage('?runId=run_1')

    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith(
      'run_1', expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(workflowApi.startWorkflowAsync).not.toHaveBeenCalled()
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(true)
    expect(wrapper.findComponent(AgentOsRunSummaryCard).exists()).toBe(true)
    expect(wrapper.text()).toContain('mission_1')
    wrapper.unmount()
  })

  it('keeps task configuration and runtime overview as independent collapsible sections', async () => {
    const { wrapper } = await mountPage('?runId=run_1')

    expect(wrapper.find('.acg-task-config-section').exists()).toBe(true)
    expect(wrapper.find('.acg-runtime-section').exists()).toBe(true)
    expect(wrapper.find('.acg-config-thumbnail').exists()).toBe(true)
    expect(wrapper.find('.acg-runtime-thumbnail').exists()).toBe(false)

    await wrapper.find('.acg-config-thumbnail .input-panel-toggle').trigger('click')
    expect(wrapper.find('.acg-config-thumbnail').exists()).toBe(false)
    expect(wrapper.find('.acg-runtime-thumbnail').exists()).toBe(false)

    await wrapper.find('.acg-runtime-expanded .runtime-panel-toggle').trigger('click')
    expect(wrapper.find('.acg-runtime-thumbnail').exists()).toBe(true)
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(true)

    await wrapper.find('.acg-runtime-thumbnail .runtime-panel-toggle').trigger('click')
    expect(wrapper.find('.acg-runtime-thumbnail').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps multiple opened Runs as editor tabs and switches or closes them locally', async () => {
    const { wrapper, router } = await mountPage('?runId=run_1')
    const vm = wrapper.vm as unknown as {
      openAcgRunFromExplorer: (runId: string) => void
    }

    vm.openAcgRunFromExplorer('run_2')
    await flushPromises()

    expect(wrapper.findAll('.workbench-editor-tab')).toHaveLength(2)
    expect(wrapper.find('.workbench-editor-tab.is-active').text()).toContain('任务 run_2')
    expect(router.currentRoute.value.query.runId).toBe('run_2')

    await wrapper.findAll('.workbench-editor-tab__main')[0].trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.runId).toBe('run_1')

    await wrapper.find('.workbench-editor-tab.is-active .workbench-editor-tab__close').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.runId).toBe('run_2')
    expect(wrapper.findAll('.workbench-editor-tab')).toHaveLength(1)
    wrapper.unmount()
  })

  it('opens the unified ACG history tab with the active Run context', async () => {
    const { wrapper, router } = await mountPage('?runId=run_1')
    const vm = wrapper.vm as unknown as {
      openOperations: () => void
      openAcgOperationsFromExplorer: () => void
    }

    vm.openOperations()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/history')
    expect(router.currentRoute.value.query).toMatchObject({ tab: 'acg', runId: 'run_1', source: 'acg' })

    await router.push('/agentos/acg')
    vm.openAcgOperationsFromExplorer()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/history')
    expect(router.currentRoute.value.query).toMatchObject({ tab: 'acg', source: 'acg' })
    wrapper.unmount()
  })

  it('keeps the Mission ID visible when the ACG projection fails', async () => {
    vi.mocked(workflowApi.getAcgView).mockRejectedValue(Object.assign(new Error('subresource missing'), {
      isAxiosError: true,
      response: { status: 404 }
    }))

    const { wrapper, router } = await mountPage('?runId=run_1')

    expect(wrapper.find('.hero-run-chip').text()).toContain('任务 ID')
    expect(wrapper.find('.hero-run-chip').text()).toContain('mission_1')
    expect(router.currentRoute.value.query.runId).toBe('run_1')
    wrapper.unmount()
  })

  it('starts a Run, writes its id to the URL and immediately connects progress polling', async () => {
    const { wrapper, router } = await mountPage()
    const draft = (wrapper.vm as unknown as { draft: { title: string; taskGoal: string } }).draft
    draft.title = '测试任务实施方案'
    draft.taskGoal = '输出可验收的实施方案'
    await wrapper.vm.$nextTick()

    const startButton = wrapper.findAll('button').find(item => item.text().includes('启动 ACG'))
    expect(startButton).toBeTruthy()
    await startButton!.trigger('click')
    await flushPromises()

    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledWith(
      expect.objectContaining({ title: '测试任务实施方案', domain: 'general' }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith(
      'run_1', expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(router.currentRoute.value.query.runId).toBe('run_1')
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(true)
    wrapper.unmount()
  })

  it('restores a Legacy ACG submission and reconciles its accepted result without another create', async () => {
    const attempt = createMissionLaunchAttempt({ slot: 'legacy-acg' })
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(new Error('lost acceptance'))
    await expect(attempt.launch(legacyAcgLaunchCommand({ ...createNativeWorkbenchDraft(), title: '原任务', taskGoal: '原目标' }, []))).rejects.toThrow()
    const accepted = run({ status: 'pending', lifecyclePhase: 'planning' })
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'CREATED', missionId: accepted.missionId, runId: accepted.runId, run: accepted })
    const { wrapper, router } = await mountPage()
    expect((wrapper.vm as any).draft.taskGoal).toBe('原目标')
    await wrapper.findAll('button').find(button => button.text() === '核对并恢复原提交')!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.query.runId).toBe(accepted.runId)
    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledTimes(1)
    expect(attempt.pending()).toBeNull()
    wrapper.unmount()
  })

  it('refreshes the ACG detail when the runtime revision changes during the same phase', async () => {
    vi.useFakeTimers()
    vi.mocked(workflowApi.getWorkflowProgress)
      .mockResolvedValueOnce(progress({ runtimeRevision: 1, updatedAt: '2026-08-20T00:01:01Z' }))
      .mockResolvedValueOnce(progress({ runtimeRevision: 2, updatedAt: '2026-08-20T00:01:02Z', completedSteps: 3 }))
    vi.mocked(workflowApi.getRun)
      .mockResolvedValueOnce(run({ runtimeRevision: 1, updatedAt: '2026-08-20T00:01:01Z' }))
      .mockResolvedValueOnce(run({ runtimeRevision: 2, updatedAt: '2026-08-20T00:01:02Z', completedStepIds: ['step_1', 'step_2', 'step_3'] }))

    const { wrapper } = await mountPage('?runId=run_1')
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()

    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledTimes(2)
    expect(workflowApi.getAcgView.mock.calls.length).toBeGreaterThanOrEqual(2)
    wrapper.unmount()
  })

  it('reruns the current configuration as a new Run under the same Mission', async () => {
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress({
      status: 'completed', phase: 'completed', percent: 100
    }))
    vi.mocked(workflowApi.getRun).mockResolvedValue(run({
      status: 'completed', lifecyclePhase: 'completed'
    }))
    const { wrapper, router } = await mountPage('?runId=run_1')
    const draft = (wrapper.vm as unknown as { draft: { title: string; taskGoal: string } }).draft
    draft.title = '测试任务实施方案'
    draft.taskGoal = '输出可验收的实施方案'
    await wrapper.vm.$nextTick()

    const rerunButton = wrapper.findAll('button').find(item => item.text().includes('基于当前配置重新运行'))
    expect(rerunButton).toBeTruthy()
    await rerunButton!.trigger('click')
    await flushPromises()

    expect(workflowApi.startWorkflowAsync).not.toHaveBeenCalled()
    expect(workflowApi.rerunWorkflowAsync).toHaveBeenCalledWith(
      'mission_1',
      expect.objectContaining({
        sourceRunId: 'run_1',
        rerunReason: 'current_configuration',
        input: expect.objectContaining({ taskName: '测试任务实施方案' })
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(router.currentRoute.value.query.runId).toBe('run_2')
    wrapper.unmount()
  })

  it('resumes a failed Run from its failed step without replaying the whole configuration', async () => {
    vi.mocked(chooseFailedRunRetryMode).mockResolvedValue('successor_run')
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress({
      status: 'failed', phase: 'failed', percent: 60, failedSteps: 1
    }))
    vi.mocked(workflowApi.getRun).mockResolvedValue(run({
      status: 'failed',
      lifecyclePhase: 'failed',
      runtimeRevision: 12,
      steps: [
        { stepId: 'source', name: 'source', agentName: 'native', status: 'completed' },
        { stepId: 'design', name: 'design', agentName: 'native', status: 'failed' },
        { stepId: 'final', name: 'final', agentName: 'native', status: 'pending' }
      ]
    }))
    const { wrapper, router } = await mountPage('?runId=run_1')

    const resumeButton = wrapper.findAll('button').find(item => item.text().includes('从失败处继续'))
    expect(resumeButton).toBeTruthy()
    await resumeButton!.trigger('click')
    await flushPromises()

    expect(workflowApi.rerunWorkflowAsync).not.toHaveBeenCalled()
    expect(workflowApi.retryWorkflowStepAsync).toHaveBeenCalledWith(
      'run_1',
      'design',
      expect.objectContaining({
        reason: 'resume_failed',
        expectedRuntimeRevision: 12,
        mode: 'successor_run',
        clientRequestId: expect.any(String)
      }),
      expect.objectContaining({ signal: expect.any(AbortSignal) })
    )
    expect(router.currentRoute.value.query.runId).toBe('run_2')
    wrapper.unmount()
  })

  it('removes a missing URL Run instead of leaving a stale progress shell', async () => {
    vi.mocked(workflowApi.getWorkflowProgress).mockRejectedValue(Object.assign(new Error('missing'), {
      isAxiosError: true,
      response: { status: 404 }
    }))
    const { wrapper, router } = await mountPage('?runId=run_missing')
    await flushPromises()

    expect(router.currentRoute.value.query.runId).toBeUndefined()
    expect(workflowApi.startWorkflowAsync).not.toHaveBeenCalled()
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(false)
    wrapper.unmount()
  })
})
