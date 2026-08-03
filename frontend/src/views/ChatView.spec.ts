import { reactive } from 'vue'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessageBox } from 'element-plus'
import { agentosApi, type AcgView, type WorkflowRun } from '@/services/api/agentos'
import { workflowApi, type WorkflowProgress } from '@/services/api/workflow'
import WorkflowProgressBar from '@/components/agentos/WorkflowProgressBar.vue'
import DynamicRunSummaryCard from '@/components/agentos/DynamicRunSummaryCard.vue'
import RoleTemplateSwitchDialog from '@/components/RoleTemplateSwitchDialog.vue'
import LawyerSkillPanel from '@/components/agent/LawyerSkillPanel.vue'
import GenericArtifactPanel from '@/features/acg/GenericArtifactPanel.vue'
import MessageBubble from '@/components/MessageBubble.vue'
import ChatView from './ChatView.vue'

let chatStoreMock: ReturnType<typeof createChatStoreMock>
let roleStoreMock: ReturnType<typeof createRoleStoreMock>

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/stores/chat', () => ({ useChatStore: () => chatStoreMock }))
vi.mock('@/stores/role', () => ({ useRoleStore: () => roleStoreMock }))
vi.mock('@/services/api/workflow', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api/workflow')>()
  return {
    ...actual,
    workflowApi: {
      ...actual.workflowApi,
      startWorkflow: vi.fn(),
      getWorkflowProgress: vi.fn()
    }
  }
})

const binding = (conversationId: string, runId: string, status = 'pending') => ({
  conversationId,
  messageId: `message_${runId}`,
  taskId: `task_${runId}`,
  acgTaskId: runId,
  runId,
  workflowId: 'legal_case_analysis_v1',
  clientRequestId: `request_${runId}`,
  source: 'agent' as const,
  createdAt: '2026-07-22T00:00:00Z',
  status
})

function createChatStoreMock() {
  const bindings: Record<string, ReturnType<typeof binding>[]> = {}
  return reactive({
    messages: [] as Array<Record<string, unknown>>,
    loading: false,
    isStreaming: false,
    isLoadingConversation: false,
    contextId: null as string | null,
    currentRoleId: null as string | null,
    workflowBindings: bindings,
    upgradeToWorkflow: vi.fn(),
    startAgentRun: vi.fn(),
    getActiveWorkflowBinding: vi.fn((conversationId: string) =>
      [...(bindings[conversationId] || [])].reverse().find(item => !['completed', 'failed', 'cancelled'].includes(item.status))
    ),
    getLatestWorkflowBinding: vi.fn((conversationId: string) => [...(bindings[conversationId] || [])].reverse()[0]),
    updateWorkflowBindingStatus: vi.fn(),
    markWorkflowBindingInvalid: vi.fn(),
    loadHistory: vi.fn(async (contextId: string) => { chatStoreMock.contextId = contextId }),
    clearMessages: vi.fn(() => {
      chatStoreMock.messages = []
      chatStoreMock.contextId = null
    }),
    setRole: vi.fn(),
    sendLawyerMessage: vi.fn(),
    sendTeacherMessage: vi.fn(),
    sendProgrammerMessage: vi.fn(),
    sendWriterMessage: vi.fn(),
    sendMessageStream: vi.fn()
  })
}

function createRoleStoreMock() {
  return reactive({
    roles: [
      { id: 'role_1', name: '律师' },
      { id: 'role_2', name: '教师' }
    ],
    currentRole: { id: 'role_1', name: '律师' },
    loadRoles: vi.fn().mockResolvedValue(undefined),
    setCurrentRole: vi.fn().mockResolvedValue(undefined),
    clearCurrentRole: vi.fn(() => { roleStoreMock.currentRole = null })
  })
}

const progress = (overrides: Partial<WorkflowProgress> = {}): WorkflowProgress => ({
  taskId: 'task_run_1', runId: 'run_1', workflowId: 'legal_case_analysis_v1', status: 'running',
  phase: 'planning', message: '正在规划', percent: null,
  totalSteps: 0, pendingSteps: 0, runningSteps: 0, waitingReviewSteps: 0,
  retryingSteps: 0, failedSteps: 0, completedSteps: 0, cancelledSteps: 0,
  currentStepId: null, activeStepIds: [], recoveryCount: 0,
  startedAt: '2026-07-22T00:00:00Z', updatedAt: '2026-07-22T00:00:01Z',
  progress: 0, percentage: 0,
  ...overrides
})

const run = (runId = 'run_1'): WorkflowRun => ({
  runId, taskId: `task_${runId}`, workflowId: 'legal_case_analysis_v1', domain: 'legal',
  status: 'completed', reviewMode: 'human_in_loop', input: {}, output: {}, steps: [], checkpoints: [], trace: []
})

const acg = (runId = 'run_1'): AcgView => ({
  runId, status: 'completed', engine: 'acg', acgBlueprint: null,
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
  props: ['disabled', 'loading'], emits: ['click'],
  template: '<button type="button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
}
const inputStub = {
  name: 'ElInput', props: ['modelValue'], emits: ['update:modelValue'],
  template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />'
}

const mountPage = async (query = '?workspace=agent&contextId=conversation_1'): Promise<{ wrapper: VueWrapper; router: Router }> => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/chat', component: { template: '<div />' } }]
  })
  await router.push(`/chat${query}`)
  await router.isReady()
  const wrapper = shallowMount(ChatView, {
    global: {
      plugins: [router],
      mocks: { $t: (key: string) => key },
      stubs: {
        'el-button': buttonStub,
        'el-input': inputStub,
        'el-icon': true,
        'el-drawer': true,
        'el-dialog': true,
        'el-select': true,
        'el-option': true,
        'el-tag': true,
        'el-collapse': true,
        'el-collapse-item': true,
        'el-avatar': true
      }
    }
  })
  await flushPromises()
  return { wrapper, router }
}

const setInputAndUpgrade = async (wrapper: VueWrapper, text = '请升级为 ACG') => {
  const input = wrapper.get('.composer-card textarea')
  await input.setValue(text)
  const button = wrapper.findAll('button').find(item => item.text().includes('Workflow'))
  if (!button) throw new Error('Workflow button not found')
  await button.trigger('click')
  await flushPromises()
}

describe('ChatView ACG progress integration', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    chatStoreMock = createChatStoreMock()
    roleStoreMock = createRoleStoreMock()
    vi.clearAllMocks()
    vi.stubGlobal('ResizeObserver', class {
      observe() {}
      disconnect() {}
    })
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({ matches: true, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
    })
    HTMLElement.prototype.scrollTo = vi.fn()
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress())
    vi.spyOn(agentosApi, 'getWorkflowRun').mockResolvedValue(run())
    vi.spyOn(agentosApi, 'getAcgView').mockResolvedValue(acg())
    chatStoreMock.startAgentRun.mockResolvedValue({
      response: {
        accepted: true,
        acgTaskId: 'run_1',
        task: { taskId: 'task_run_1', status: 'pending' },
        run: { runId: 'run_1', workflowId: 'legal_case_analysis_v1', status: 'pending' }
      },
      binding: binding('conversation_1', 'run_1')
    })
  })

  it('keeps Agent idle state centered until the first message starts the session', async () => {
    const { wrapper } = await mountPage('?workspace=agent')

    expect(wrapper.get('.chat-panel').classes()).toContain('hero-mode')
    expect(wrapper.text()).not.toContain('下一步推荐')
    expect(wrapper.find('.recommendation-panel-wrap').exists()).toBe(false)
    expect(wrapper.find('.context-panel').exists()).toBe(false)
    expect(wrapper.find('.workflow-acg-panel').exists()).toBe(false)
    expect(wrapper.get('.agent-panel').classes()).toContain('collapsed')

    await wrapper.get('.agent-panel-toggle').trigger('click')

    expect(wrapper.get('.chat-panel').classes()).toContain('hero-mode')
    expect(wrapper.get('.agent-panel').classes()).not.toContain('collapsed')
    expect(wrapper.find('.agent-panel-content').exists()).toBe(true)
    expect(wrapper.get('.agent-panel-content').attributes('style') || '').not.toContain('display: none')

    await wrapper.get('.context-panel-dock').trigger('click')
    expect(wrapper.get('.chat-panel').classes()).toContain('hero-mode')
    expect(wrapper.find('.context-panel').exists()).toBe(true)

    await wrapper.get('.workflow-acg-dock').trigger('click')
    expect(wrapper.get('.chat-panel').classes()).toContain('hero-mode')
    expect(wrapper.find('.workflow-acg-panel').exists()).toBe(true)

    chatStoreMock.messages.push({ id: 'message_1', role: 'user', content: '开始任务' })
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.chat-panel').classes()).not.toContain('hero-mode')
    expect(wrapper.find('.context-panel').exists()).toBe(true)
    expect(wrapper.find('.workflow-acg-panel').exists()).toBe(true)
  })

  it('shows distinct general interfaces for Agent and Chat without auto-selecting a role', async () => {
    roleStoreMock.currentRole = null
    const { wrapper, router } = await mountPage('?workspace=agent')

    expect(wrapper.text()).toContain('通用 Agent 对话')
    expect(wrapper.get('.composer-agent-mode').text()).toContain('通用 Agent')
    expect(roleStoreMock.setCurrentRole).not.toHaveBeenCalled()
    expect(chatStoreMock.setRole).toHaveBeenCalledWith(null)

    await router.push('/chat?workspace=chat')
    window.dispatchEvent(new CustomEvent('workspace-mode-change', { detail: 'chat' }))
    await flushPromises()

    expect(wrapper.text()).toContain('通用 Chat 对话')
    expect(wrapper.get('.composer-agent-mode').text()).toContain('通用 Chat')
    wrapper.unmount()
  })

  it('uses the current workspace name in vertical-role conversation titles', async () => {
    roleStoreMock.currentRole = { id: 'role_2', name: '教师' }
    const { wrapper, router } = await mountPage('?workspace=chat')

    expect(wrapper.text()).toContain('教师 Chat 对话')
    expect(wrapper.text()).not.toContain('教师 Agent 对话')

    await router.push('/chat?workspace=agent')
    window.dispatchEvent(new CustomEvent('workspace-mode-change', { detail: 'agent' }))
    await flushPromises()

    expect(wrapper.text()).toContain('教师 Agent 对话')
    wrapper.unmount()
  })

  it('routes a general Agent task through dynamic ACG parameters', async () => {
    roleStoreMock.currentRole = null
    const { wrapper } = await mountPage('?workspace=agent')
    await wrapper.get('.composer-card textarea').setValue('制定一个跨部门产品发布计划')
    await wrapper.get('.composer-send').trigger('click')
    await flushPromises()

    expect(chatStoreMock.startAgentRun).toHaveBeenCalledWith(
      '制定一个跨部门产品发布计划',
      expect.objectContaining({
        domain: 'general',
        intent: 'general',
        workflowId: undefined,
        reviewMode: 'auto'
      })
    )
    wrapper.unmount()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('starts asynchronously, creates a binding, writes query, and starts Progress immediately', async () => {
    const { wrapper, router } = await mountPage()
    await setInputAndUpgrade(wrapper)

    expect(chatStoreMock.startAgentRun).toHaveBeenCalledWith('请升级为 ACG', expect.objectContaining({
      conversationId: 'conversation_1',
      clientRequestId: expect.any(String)
    }))
    expect(workflowApi.startWorkflow).not.toHaveBeenCalled()
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run_1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(router.currentRoute.value.query.runId).toBe('run_1')
    expect(agentosApi.getAcgView).not.toHaveBeenCalled()
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(true)
    wrapper.unmount()
  })

  it('keeps Chat streaming independent from Workflow planning', async () => {
    chatStoreMock.loading = true
    chatStoreMock.isStreaming = true
    const { wrapper } = await mountPage()
    await setInputAndUpgrade(wrapper, '流式聊天期间启动')

    expect(chatStoreMock.startAgentRun).toHaveBeenCalledOnce()
    expect(chatStoreMock.isStreaming).toBe(true)
    expect(wrapper.findComponent(WorkflowProgressBar).props('progress')).toEqual(expect.objectContaining({ phase: 'planning' }))
    wrapper.unmount()
  })

  it('opens the role template dialog from the composer and applies a selected role', async () => {
    const { wrapper } = await mountPage('?workspace=agent')
    const trigger = wrapper.get('.composer-agent-mode')

    expect(trigger.attributes('aria-haspopup')).toBe('dialog')
    await trigger.trigger('click')

    const dialog = wrapper.findComponent(RoleTemplateSwitchDialog)
    expect(dialog.props('open')).toBe(true)

    dialog.vm.$emit('confirm', { roleId: 'teacher', templateKey: 'teacher-lesson' })
    await flushPromises()

    expect(roleStoreMock.setCurrentRole).toHaveBeenCalledWith(expect.objectContaining({ id: 'role_2', name: '教师' }))
    expect(chatStoreMock.setRole).toHaveBeenCalledWith('role_2')
    expect(localStorage.getItem('chat.active_template_key')).toBe('teacher-lesson')
    expect(dialog.props('open')).toBe(false)
    wrapper.unmount()
  })

  it('creates a fresh Agent context when switching roles and preserves the old run in history', async () => {
    chatStoreMock.messages = [{ id: 'message_1', role: 'user', content: '旧任务' }]
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'run_1', 'completed')]
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const { wrapper, router } = await mountPage('?workspace=agent&contextId=conversation_1&runId=run_1')

    await wrapper.get('.composer-agent-mode').trigger('click')
    const dialog = wrapper.findComponent(RoleTemplateSwitchDialog)
    dialog.vm.$emit('confirm', { roleId: 'teacher', templateKey: 'teacher-lesson' })
    await flushPromises()

    expect(confirm).toHaveBeenCalledWith(
      expect.stringContaining('当前 Agent 任务会保留在记录中'),
      '切换角色与模板',
      expect.objectContaining({ confirmButtonText: '新建并切换' })
    )
    expect(chatStoreMock.clearMessages).toHaveBeenCalledOnce()
    expect(roleStoreMock.setCurrentRole).toHaveBeenCalledWith(expect.objectContaining({ id: 'role_2' }))
    expect(router.currentRoute.value.query).toEqual({ workspace: 'agent' })
    expect(chatStoreMock.markWorkflowBindingInvalid).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows idempotency conflict without falling back to synchronous start', async () => {
    chatStoreMock.startAgentRun.mockRejectedValue({ isAxiosError: true, response: { status: 409 } })
    const { wrapper } = await mountPage()
    await setInputAndUpgrade(wrapper)

    expect(wrapper.text()).toContain('本次请求标识与原任务参数冲突')
    expect(workflowApi.startWorkflow).not.toHaveBeenCalled()
    expect(workflowApi.getWorkflowProgress).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('reuses clientRequestId when a temporarily unavailable submission is retried', async () => {
    chatStoreMock.startAgentRun
      .mockRejectedValueOnce({ isAxiosError: true, response: { status: 503 } })
      .mockResolvedValueOnce({
        response: {
          accepted: true,
          acgTaskId: 'run_1',
          task: { taskId: 'task_run_1', status: 'pending' },
          run: { runId: 'run_1', workflowId: 'legal_case_analysis_v1', status: 'pending' }
        },
        binding: binding('conversation_1', 'run_1')
      })
    const { wrapper } = await mountPage()
    await setInputAndUpgrade(wrapper, '可恢复提交')
    expect(wrapper.text()).toContain('ACG 任务暂时不可用')
    const firstRequestId = chatStoreMock.startAgentRun.mock.calls[0][1].clientRequestId

    await setInputAndUpgrade(wrapper, '可恢复提交')
    const secondRequestId = chatStoreMock.startAgentRun.mock.calls[1][1].clientRequestId
    expect(secondRequestId).toBe(firstRequestId)
    wrapper.unmount()
  })

  it('switches conversation polling without allowing the old Run to overwrite the new one', async () => {
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'run_1')]
    chatStoreMock.workflowBindings.conversation_2 = [binding('conversation_2', 'run_2')]
    vi.mocked(workflowApi.getWorkflowProgress).mockImplementation(runId => Promise.resolve(progress({
      runId,
      taskId: `task_${runId}`,
      percent: runId === 'run_2' ? 40 : null,
      phase: runId === 'run_2' ? 'executing' : 'planning'
    })))
    const { wrapper, router } = await mountPage()
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run_1', expect.any(Object))
    vi.mocked(workflowApi.getWorkflowProgress).mockClear()
    await router.push('/chat?workspace=agent&contextId=conversation_2')
    await flushPromises()

    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run_2', expect.any(Object))
    expect(wrapper.findComponent(WorkflowProgressBar).props('progress')).toEqual(expect.objectContaining({ runId: 'run_2' }))
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('treats an explicit history runId as authoritative over a stale conversation binding', async () => {
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'run_old')]
    vi.mocked(workflowApi.getWorkflowProgress).mockImplementation(runId => Promise.resolve(progress({
      runId,
      taskId: `task_${runId}`
    })))
    vi.mocked(agentosApi.getWorkflowRun).mockImplementation(runId => Promise.resolve(run(runId)))
    vi.mocked(agentosApi.getAcgView).mockImplementation(runId => Promise.resolve(acg(runId)))

    const { wrapper, router } = await mountPage('?workspace=agent&contextId=conversation_1&runId=run_selected')
    await flushPromises()

    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run_selected', expect.any(Object))
    expect(agentosApi.getAcgView).toHaveBeenCalledWith('run_selected', expect.any(Object))
    expect(router.currentRoute.value.query.runId).toBe('run_selected')
    wrapper.unmount()
  })

  it('renders the saved task input and final deliverable when an Agent history run has no chat messages', async () => {
    roleStoreMock.currentRole = null
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue({
      ...run('run_history'),
      domain: 'general',
      workflowId: 'native_acg_runtime_v1',
      input: { userIntent: '审查软件开发合同并生成可追溯报告' },
      steps: [{
        stepId: 'report_generate',
        name: '生成报告',
        agentName: 'Report Agent',
        status: 'completed',
        output: {
          artifact: {
            artifactId: 'artifact_history',
            type: 'report',
            title: '合同审查报告',
            mediaType: 'text/markdown',
            content: '# 合同审查报告',
            structuredData: { executiveSummary: '发现高风险条款。' }
          }
        }
      }]
    })
    vi.mocked(agentosApi.getAcgView).mockResolvedValue({
      ...acg('run_history'),
      finalArtifacts: [{
        artifactId: 'legacy_projection',
        type: 'report',
        title: 'Workflow final report',
        mediaType: 'text/markdown',
        content: '# Legacy report',
        structuredData: {},
        legacy: true
      }],
      finalReport: null
    })
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress({
      runId: 'run_history',
      taskId: 'task_run_history',
      status: 'completed',
      phase: 'completed',
      totalSteps: 1,
      completedSteps: 1
    }))

    const { wrapper } = await mountPage('?workspace=agent&runId=run_history')
    await flushPromises()

    expect(wrapper.get('.workflow-history-detail').text()).toContain('审查软件开发合同并生成可追溯报告')
    const artifactPanel = wrapper.findComponent(GenericArtifactPanel)
    expect(artifactPanel.props('stepOutputs')).toHaveLength(1)
    expect(artifactPanel.props('finalArtifacts')).toEqual([
      expect.objectContaining({ artifactId: 'artifact_history', content: '# 合同审查报告' })
    ])
    expect(chatStoreMock.messages).toHaveLength(0)
    wrapper.unmount()
  })

  it('hydrates contract-review ACG artifacts for the lawyer result panel on history restore', async () => {
    roleStoreMock.currentRole = null
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue({
      ...run('run_contract'),
      status: 'waiting_review',
      steps: [
        { stepId: 'contract_parse', name: '合同解析', agentName: '合同解析 Agent', status: 'completed' },
        { stepId: 'risk_detect', name: '风险识别', agentName: '风险识别 Agent', status: 'waiting_review' }
      ],
      output: {
        artifacts: {
          risk_detect: { risks: [{ id: 'risk_1', title: '付款与验收倒挂', level: 'high' }] },
          legal_evidence_match: { evidences: [{ id: 'evidence_1', sourceName: '民法典' }] },
          report_generate: { report_markdown: '# 合同审查报告' }
        }
      }
    })
    vi.mocked(agentosApi.getAcgView).mockResolvedValue(acg('run_contract'))
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress({
      runId: 'run_contract',
      taskId: 'task_run_contract',
      status: 'waiting_review',
      phase: 'review'
    }))

    const { wrapper } = await mountPage('?workspace=agent&runId=run_contract')
    await flushPromises()

    expect(agentosApi.getWorkflowRun).toHaveBeenCalledWith('run_contract', expect.any(Object))
    expect(agentosApi.getAcgView).toHaveBeenCalledWith('run_contract', expect.any(Object))
    const lawyerPanel = wrapper.findComponent(LawyerSkillPanel)
    expect(lawyerPanel.props('resultCount')).toBe(3)
    expect(lawyerPanel.props('skillsUsed')).toEqual(['contract_parse', 'risk_detect'])
    expect(lawyerPanel.props('trace')).toHaveLength(2)
    expect(lawyerPanel.props('riskLevel')).toBe('high')
    const historyMessages = wrapper.findAllComponents(MessageBubble)
    expect(historyMessages).toHaveLength(2)
    expect(historyMessages[0].props('message')).toEqual(expect.objectContaining({ role: 'user' }))
    expect(historyMessages[1].props('message')).toEqual(expect.objectContaining({
      role: 'assistant',
      content: '# 合同审查报告'
    }))
    expect(wrapper.findComponent(DynamicRunSummaryCard).exists()).toBe(false)
    await wrapper.get('.lawyer-workflow-progress__toggle').trigger('click')
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(false)
    expect(wrapper.get('.lawyer-workflow-progress__collapsed-row').text()).toContain('ACG 执行状态')
    expect(localStorage.getItem('chat.lawyer_workflow_progress_collapsed')).toBe('1')
    await wrapper.get('.lawyer-workflow-progress__collapsed-row').trigger('click')
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(true)
    expect(wrapper.findComponent(GenericArtifactPanel).exists()).toBe(false)
    expect(wrapper.text()).toContain('律师模式')
    wrapper.unmount()
  })

  it('marks a restored binding invalid on 404 without creating a new Run', async () => {
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'run_missing')]
    vi.mocked(workflowApi.getWorkflowProgress).mockRejectedValue({ response: { status: 404 } })
    const { wrapper } = await mountPage()
    await flushPromises()

    expect(wrapper.findComponent(WorkflowProgressBar).props('syncError')).toContain('不存在或当前账户无权访问')
    expect(chatStoreMock.markWorkflowBindingInvalid).toHaveBeenCalledWith('conversation_1', 'run_missing')
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('loads terminal Run/ACG exactly once and does not cancel the backend on unmount', async () => {
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'run_1')]
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress({
      phase: 'completed', status: 'completed', percent: 100, totalSteps: 4, completedSteps: 4
    }))
    const { wrapper } = await mountPage()
    await flushPromises()

    expect(agentosApi.getWorkflowRun).toHaveBeenCalledTimes(1)
    expect(agentosApi.getAcgView).toHaveBeenCalledTimes(1)
    wrapper.unmount()
    expect(agentosApi.getWorkflowRun).toHaveBeenCalledTimes(1)
  })
})
