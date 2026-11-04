import { reactive } from 'vue'
import { flushPromises, shallowMount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { agentosApi, type AcgView, type WorkflowRun } from '@/services/api/agentos'
import { workflowApi, type WorkflowProgress } from '@/services/api/workflow'
import { conversationApi } from '@/services/api/conversation'
import WorkflowProgressBar from '@/components/agentos/WorkflowProgressBar.vue'
import AcgRunInspector from '@/components/agentos/AcgRunInspector.vue'
import GenericArtifactPanel from '@/features/acg/GenericArtifactPanel.vue'
import ChatView from './ChatView.vue'
import NativeWorkspacePicker from '@/components/platform/NativeWorkspacePicker.vue'
import { capabilitiesFixture } from '@/test/fixtures/runCapabilities'

let chatStoreMock: ReturnType<typeof createChatStoreMock>

vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/stores/chat', () => ({ useChatStore: () => chatStoreMock }))
vi.mock('@/services/api/conversation', () => ({
  conversationApi: {
    getUserConversations: vi.fn()
  }
}))
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
  missionId: `mission_${runId}`,
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
    conversationWorkspaceMode: null as 'agent' | 'chat' | null,
    migrateDraftBindings: vi.fn(),
    contextUsedTokens: null as number | null,
    contextWindowTokens: null as number | null,
    contextModel: null as string | null,
    contextModels: {} as Record<string, number>,
    workflowBindings: bindings,
    upgradeToWorkflow: vi.fn(),
    startAgentRun: vi.fn(),
    pendingMissionLaunch: vi.fn(() => null),
    resumeMissionLaunch: vi.fn(),
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
    fetchContextWindows: vi.fn(async () => {}),
    sendMessageStream: vi.fn()
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
  runId, missionId: `mission_${runId}`, taskId: `task_${runId}`, workflowId: 'legal_case_analysis_v1', domain: 'legal',
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
        FormalExecutionControls: false,
        PermissionSelector: false,
        AcgRunInspector: { ...AcgRunInspector, name: 'AcgRunInspector', template: '<div />' },
        GenericArtifactPanel: { ...GenericArtifactPanel, name: 'GenericArtifactPanel', template: '<div />' },
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
  await vi.dynamicImportSettled()
  await flushPromises()
  return { wrapper, router }
}

const setInputAndUpgrade = async (wrapper: VueWrapper, text = '请升级为 ACG') => {
  const input = wrapper.get('.composer-card textarea')
  await input.setValue(text)
  await wrapper.get('.composer-send').trigger('click')
  await flushPromises()
}

describe('ChatView ACG progress integration', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    chatStoreMock = createChatStoreMock()
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
    vi.spyOn(agentosApi, 'getWorkflowRun').mockImplementation(async id => run(id))
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

  it('writes the first chat context into the URL, preserving queries, without reloading its messages', async () => {
    chatStoreMock.sendMessageStream.mockImplementation(async () => {
      chatStoreMock.messages.push({ id: 'reply', role: 'assistant', content: 'original reply' })
      chatStoreMock.contextId = 'ctx-first'
    })
    const { wrapper, router } = await mountPage('?workspace=chat&keep=value')
    await wrapper.get('.composer-card textarea').setValue('hello')
    await wrapper.get('.composer-send').trigger('click'); await flushPromises()
    expect(router.currentRoute.value.query).toEqual({ workspace: 'chat', keep: 'value', contextId: 'ctx-first' })
    expect(chatStoreMock.messages[0].content).toBe('original reply')
    expect(chatStoreMock.loadHistory).not.toHaveBeenCalled()
    expect(chatStoreMock.migrateDraftBindings).toHaveBeenCalledWith(expect.stringMatching(/^draft:/), 'ctx-first')
    wrapper.unmount()
  })

  it('restores the same context on refresh without merging a persisted unrelated draft or launching anything', async () => {
    localStorage.setItem('chat.workflow_draft_conversation_id', 'draft:unproven')
    const uuid = vi.spyOn(crypto, 'randomUUID')
    const { wrapper, router } = await mountPage('?workspace=chat&contextId=ctx-original&keep=value')
    expect(chatStoreMock.loadHistory).toHaveBeenCalledTimes(1)
    expect(chatStoreMock.loadHistory).toHaveBeenCalledWith('ctx-original')
    expect(router.currentRoute.value.query.contextId).toBe('ctx-original')
    expect(chatStoreMock.migrateDraftBindings).not.toHaveBeenCalled()
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    expect(chatStoreMock.upgradeToWorkflow).not.toHaveBeenCalled()
    expect(chatStoreMock.sendMessageStream).not.toHaveBeenCalled()
    expect(uuid).not.toHaveBeenCalled()
    uuid.mockRestore(); wrapper.unmount()
  })

  it.each(['chat', 'agent'] as const)('consumes the Shell new-conversation route intent in %s mode exactly once', async mode => {
    localStorage.setItem('chat.workflow_draft_conversation_id', 'draft:old')
    chatStoreMock.contextId = 'ctx-old'
    chatStoreMock.messages.push({ id: 'old-message', role: 'assistant', content: 'old' })
    chatStoreMock.workflowBindings['ctx-old'] = [binding('ctx-old', 'run-old')]
    const oldDraftBinding = { ...binding('ctx-old', 'run-old-draft'), conversationAliases: ['draft:old'] }
    chatStoreMock.workflowBindings['ctx-old'].push(oldDraftBinding)

    const { wrapper, router } = await mountPage(`?workspace=${mode}&contextId=ctx-old&missionId=mission-old&runId=run-old&newConversation=1&keep=value`)
    const newDraftId = localStorage.getItem('chat.workflow_draft_conversation_id')

    expect(newDraftId).toMatch(/^draft:/)
    expect(newDraftId).not.toBe('draft:old')
    expect(chatStoreMock.clearMessages).toHaveBeenCalledTimes(1)
    expect(chatStoreMock.workflowBindings['ctx-old']).toEqual(expect.arrayContaining([
      expect.objectContaining({
        conversationId: 'ctx-old', runId: 'run-old-draft', conversationAliases: ['draft:old']
      })
    ]))
    expect(router.currentRoute.value.query).toEqual({ workspace: mode, keep: 'value' })
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('resets a reused ChatView when Shell changes workspace mode and does not clear twice', async () => {
    localStorage.setItem('chat.workflow_draft_conversation_id', 'draft:before-mode')
    chatStoreMock.contextId = 'ctx-before-mode'
    const { wrapper, router } = await mountPage('?workspace=chat&contextId=ctx-before-mode')
    const before = localStorage.getItem('chat.workflow_draft_conversation_id')
    chatStoreMock.clearMessages.mockClear()

    window.dispatchEvent(new CustomEvent('workspace-mode-change', { detail: { mode: 'agent' } }))
    await router.replace({ path: '/chat', query: { workspace: 'agent', newConversation: '1', keep: 'value' } })
    await flushPromises()

    expect(localStorage.getItem('chat.workflow_draft_conversation_id')).not.toBe(before)
    expect(chatStoreMock.clearMessages).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.query).toEqual({ workspace: 'agent', keep: 'value' })
    wrapper.unmount()
  })

  it('consumes a same-mode Shell new-chat route marker in an already mounted ChatView', async () => {
    localStorage.setItem('chat.workflow_draft_conversation_id', 'draft:previous')
    chatStoreMock.contextId = 'ctx-previous'
    const { wrapper, router } = await mountPage('?workspace=chat&contextId=ctx-previous')
    const previousDraft = localStorage.getItem('chat.workflow_draft_conversation_id')
    chatStoreMock.clearMessages.mockClear()

    await router.push({ path: '/chat', query: { workspace: 'chat', newConversation: '1' } })
    await flushPromises()

    expect(localStorage.getItem('chat.workflow_draft_conversation_id')).not.toBe(previousDraft)
    expect(chatStoreMock.clearMessages).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.query).toEqual({ workspace: 'chat' })
    wrapper.unmount()
  })

  it('restores only the new draft task and still resolves the old task through its original context', async () => {
    localStorage.setItem('chat.workflow_draft_conversation_id', 'draft:old')
    chatStoreMock.contextId = 'ctx-old'
    chatStoreMock.workflowBindings['ctx-old'] = [{
      ...binding('ctx-old', 'run-old'), missionId: 'mission_run-old',
      conversationAliases: ['draft:old']
    }]
    const { wrapper, router } = await mountPage('?workspace=agent&contextId=ctx-old')
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run-old', expect.any(Object))
    chatStoreMock.clearMessages()
    chatStoreMock.migrateDraftBindings.mockClear()
    await router.push({ path: '/chat', query: { workspace: 'agent', newConversation: '1' } })
    await flushPromises()
    const newDraft = localStorage.getItem('chat.workflow_draft_conversation_id')!
    expect(newDraft).not.toBe('draft:old')
    chatStoreMock.workflowBindings[newDraft] = [
      { ...binding(newDraft, 'run-new'), missionId: 'mission_run-new' }
    ]
    await router.push({ path: '/chat', query: { workspace: 'agent', missionId: 'mission_run-new', runId: 'run-new' } })
    await flushPromises()
    expect(chatStoreMock.getActiveWorkflowBinding).toHaveBeenCalledWith(newDraft)
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run-new', expect.any(Object))
    expect(router.currentRoute.value.query.runId).toBe('run-new')

    vi.mocked(workflowApi.getWorkflowProgress).mockClear()
    await router.push({ path: '/chat', query: { workspace: 'agent', contextId: 'ctx-old' } })
    await flushPromises()
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run-old', expect.any(Object))
    expect(workflowApi.getWorkflowProgress).not.toHaveBeenCalledWith('run-new', expect.any(Object))
    expect(chatStoreMock.getActiveWorkflowBinding).toHaveBeenCalledWith('ctx-old')
    wrapper.unmount()
  })

  it.each(['chat', 'agent'] as const)('does not let an obsolete %s composer failure restore old input or unlock a newer send', async mode => {
    let failOld!: (error: Error) => void
    let finishNew!: () => void
    const send = mode === 'chat' ? chatStoreMock.sendMessageStream : chatStoreMock.startAgentRun
    send
      .mockImplementationOnce(() => new Promise<void>((_ok, fail) => { failOld = fail }))
      .mockImplementationOnce(() => new Promise<void>(ok => { finishNew = ok }))
    const { wrapper, router } = await mountPage(`?workspace=${mode}`)
    await wrapper.get('.composer-card textarea').setValue('old input')
    await wrapper.get('.composer-send').trigger('click')
    await router.push(`/chat?workspace=${mode}&newConversation=1`); await flushPromises()
    await wrapper.get('.composer-card textarea').setValue('new input')
    await wrapper.get('.composer-send').trigger('click')
    failOld(new Error('obsolete failure')); await flushPromises()
    expect((wrapper.get('.composer-card textarea').element as HTMLTextAreaElement).value).toBe('')
    await wrapper.get('.composer-card textarea').setValue('third input')
    await wrapper.get('.composer-send').trigger('click')
    expect(send).toHaveBeenCalledTimes(2)
    finishNew(); await flushPromises(); wrapper.unmount()
  })

  it('rejects an explicit Run from another Mission without falling back or creating a binding', async () => {
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'fallback')]
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue({ ...run('selected'), missionId: 'other-mission' })
    const { wrapper, router } = await mountPage('?workspace=agent&contextId=conversation_1&missionId=expected&runId=selected')
    expect(workflowApi.getWorkflowProgress).not.toHaveBeenCalled()
    expect(agentosApi.getAcgView).not.toHaveBeenCalled()
    expect(router.currentRoute.value.query.runId).toBe('selected')
    expect(chatStoreMock.workflowBindings.conversation_1).toHaveLength(1)
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('keeps the explicitly selected superseded Run while a successor binding exists', async () => {
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'old', 'superseded'), binding('conversation_1', 'latest', 'running')]
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue({ ...run('old'), status: 'superseded', lineage: { supersededByRunId: 'latest' } })
    vi.mocked(agentosApi.getAcgView).mockResolvedValue(acg('old'))
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress({ runId: 'old', status: 'superseded' }))
    const { wrapper, router } = await mountPage('?workspace=agent&contextId=conversation_1&runId=old')
    expect(router.currentRoute.value.query.runId).toBe('old')
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledTimes(1)
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('old', expect.any(Object))
    expect(agentosApi.getWorkflowRun).toHaveBeenCalledTimes(1)
    expect(agentosApi.getWorkflowRun).toHaveBeenCalledWith('old')
    wrapper.unmount()
  })

  it('selects a backend-verified active binding before a newer terminal binding', async () => {
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'active', 'running'), binding('conversation_1', 'terminal', 'succeeded')]
    vi.mocked(agentosApi.getWorkflowRun).mockImplementation(async id => ({ ...run(id), status: id === 'active' ? 'waiting_review' : 'succeeded' }))
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress({ runId: 'active', status: 'waiting_review' }))
    vi.mocked(agentosApi.getAcgView).mockResolvedValue(acg('active'))
    const { wrapper, router } = await mountPage()
    expect(router.currentRoute.value.query.runId).toBe('active')
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('active', expect.any(Object))
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('resolves an explicit Mission using its existing projection and pins the verified Run in the URL', async () => {
    const workspace = vi.spyOn(agentosApi, 'getMissionWorkspace').mockResolvedValue({
      mission: { missionId: 'mission_run_1' }, activeRun: { runId: 'run_1' }
    } as any)
    const { wrapper, router } = await mountPage('?workspace=agent&contextId=conversation_1&missionId=mission_run_1&keep=value')
    expect(workspace).toHaveBeenCalledWith('mission_run_1')
    expect(router.currentRoute.value.query).toEqual({ workspace: 'agent', contextId: 'conversation_1', missionId: 'mission_run_1', keep: 'value', runId: 'run_1' })
    expect(chatStoreMock.workflowBindings.conversation_1).toBeUndefined()
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    wrapper.unmount(); workspace.mockRestore()
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
    expect(wrapper.get('.composer-missions').classes()).toContain('is-conversation')
    expect(wrapper.findComponent(NativeWorkspacePicker).exists()).toBe(true)
  })

  it('shows distinct generic interfaces for Agent and Chat', async () => {
    const { wrapper, router } = await mountPage('?workspace=agent')

    expect(wrapper.find('.hero-greeting').exists()).toBe(true)
    expect(wrapper.get('.composer-missions').classes()).not.toContain('is-conversation')
    expect(wrapper.find('.mission-chip').exists()).toBe(false)
    expect(wrapper.findComponent(NativeWorkspacePicker).exists()).toBe(true)
    expect(wrapper.get('.composer-agent-mode').text()).toContain('请求批准')
    expect(wrapper.get('.composer-agent-mode').classes()).toContain('composer-agent-mode--permission')
    expect(wrapper.get('.composer-agent-mode').element.tagName).toBe('BUTTON')
    await wrapper.get('.composer-agent-mode').trigger('click')
    expect(wrapper.findAll('[role="menuitemradio"]')).toHaveLength(3)
    await wrapper.findAll('[role="menuitemradio"]')[2].trigger('click')
    expect(wrapper.get('.composer-agent-mode').text()).toContain('完全访问')
    expect(wrapper.find('.permission-menu').exists()).toBe(false)
    expect(wrapper.find('[aria-haspopup="dialog"]').exists()).toBe(false)

    await router.push('/chat?workspace=chat')
    window.dispatchEvent(new CustomEvent('workspace-mode-change', { detail: 'chat' }))
    await flushPromises()

    expect(wrapper.find('.hero-greeting').exists()).toBe(true)
    // Chat 模式已移除「通用 Chat」静态徽标，仅 Agent 模式保留权限选择器
    expect(wrapper.find('.composer-agent-mode').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps secondary composer controls behind the Codex-style tools button', async () => {
    const { wrapper } = await mountPage('?workspace=chat')

    expect(wrapper.find('.composer-tools-menu').exists()).toBe(false)

    await wrapper.get('.composer-tools-toggle').trigger('click')

    expect(wrapper.get('.composer-tools-menu').text()).toContain('添加文件')
    expect(wrapper.get('.composer-tools-menu').text()).toContain('模型设置')

    await wrapper.get('.composer-tools-toggle').trigger('click')
    expect(wrapper.find('.composer-tools-menu').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows the Chat conversation info rail with real session data and hides it in Agent mode', async () => {
    vi.mocked(conversationApi.getUserConversations).mockResolvedValue([
      {
        id: 'conv_1',
        userId: 'user_1',
        contextId: 'conversation_1',
        title: '**你好你好**',
        createdAt: '2026-10-02T14:53:00+08:00',
        updatedAt: '2026-10-02T14:55:00+08:00'
      }
    ])
    chatStoreMock.contextId = 'conversation_1'
    chatStoreMock.contextUsedTokens = 1280
    chatStoreMock.contextWindowTokens = 128000
    chatStoreMock.messages = [
      { id: 1, role: 'user', content: '你好', createdAt: new Date('2026-10-02T14:53:00+08:00'), tokensUsed: 120 },
      {
        id: 2,
        role: 'assistant',
        content: '你好！有什么可以帮你的？',
        createdAt: new Date('2026-10-02T14:55:00+08:00'),
        modelInfo: 'deepseek-flash',
        tokensUsed: 340,
        sources: [{ title: '产品白皮书', url: 'https://example.com/whitepaper' }]
      }
    ] as Array<Record<string, unknown>>

    vi.useFakeTimers()
    try {
      const { wrapper } = await mountPage('?workspace=chat&contextId=conversation_1')
      // 信息卡元数据走 600ms 防抖刷新（首轮回复后后端才生成标题）
      await vi.advanceTimersByTimeAsync(700)
      await flushPromises()

      expect(wrapper.find('.chat-info-dock').exists()).toBe(true)
      expect(wrapper.get('.chat-info-card__title').text()).toBe('你好你好')
      const metrics = wrapper.get('.chat-info-card__metrics').text()
      expect(metrics).toContain('deepseek-flash')
      expect(metrics).toContain('2 条 · 1 轮')
      expect(metrics).toContain('460')
      expect(metrics).toContain('上下文')
      expect(wrapper.get('.chat-info-card__sources').text()).toContain('产品白皮书')

      // 停靠宽度可调整并持久化：键盘 ±8 步进写回 localStorage 与行内样式
      const dock = wrapper.get('.chat-info-dock')
      const readDockWidth = () => Number(dock.attributes('style')?.match(/width:\s*(\d+)px/)?.[1] || 0)
      const widthBefore = readDockWidth()
      expect(widthBefore).toBeGreaterThan(0)
      expect(localStorage.getItem('chat.chat_info_width')).toBeNull()

      await dock.get('.chat-info-dock__resizer').trigger('keydown', { key: 'ArrowLeft' })
      await flushPromises()
      expect(readDockWidth()).toBe(widthBefore + 8)
      expect(localStorage.getItem('chat.chat_info_width')).toBe(String(widthBefore + 8))

      // 收起后仅剩窄轨，可再展开
      await dock.get('.chat-info-dock__collapse').trigger('click')
      await flushPromises()
      expect(wrapper.find('.chat-info-card').exists()).toBe(false)
      expect(localStorage.getItem('chat.chat_info_collapsed')).toBe('1')
      await wrapper.get('.chat-info-dock__expand').trigger('click')
      await flushPromises()
      expect(wrapper.find('.chat-info-card').exists()).toBe(true)
      wrapper.unmount()

      const agentPage = await mountPage('?workspace=agent&contextId=conversation_1')
      expect(agentPage.wrapper.find('.chat-info-dock').exists()).toBe(false)
      agentPage.wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('routes a general Agent task through dynamic ACG parameters', async () => {
    const { wrapper } = await mountPage('?workspace=agent')
    await wrapper.get('.composer-card textarea').setValue('制定一个跨部门产品发布计划')
    await wrapper.get('.composer-send').trigger('click')
    await flushPromises()

    expect(chatStoreMock.startAgentRun).toHaveBeenCalledWith(
      '制定一个跨部门产品发布计划',
      expect.objectContaining({
        policyProfile: 'conversation-workspace'
      })
    )
    wrapper.unmount()
  })

  it('keeps ordinary Chat messages on sendMessageStream without launching a Mission', async () => {
    const { wrapper } = await mountPage('?workspace=chat')
    await wrapper.get('.composer-card textarea').setValue('普通对话')
    await wrapper.get('.composer-send').trigger('click')
    await flushPromises()
    expect(chatStoreMock.sendMessageStream).toHaveBeenCalledWith('普通对话', 'default', expect.any(Object), 'chat')
    expect(chatStoreMock.upgradeToWorkflow).not.toHaveBeenCalled()
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('restores a pending Conversation goal and explicitly resumes through the Store without inventing an operation ID', async () => {
    chatStoreMock.pendingMissionLaunch.mockReturnValue({ operationId: 'original', commandSnapshot: { semantics: { objective: '恢复原需求' } } } as any)
    chatStoreMock.resumeMissionLaunch.mockResolvedValue({ binding: binding('conversation_1', 'run_1') })
    const { wrapper, router } = await mountPage()
    expect((wrapper.get('.composer-card textarea').element as HTMLTextAreaElement).value).toBe('恢复原需求')
    await wrapper.findAll('button').find(button => button.text() === '核对并恢复原提交')!.trigger('click')
    await flushPromises()
    expect(chatStoreMock.resumeMissionLaunch).toHaveBeenCalledWith('conversation_1')
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    expect(router.currentRoute.value.query.runId).toBe('run_1')
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
      conversationId: 'conversation_1'
    }))
    expect(workflowApi.startWorkflow).not.toHaveBeenCalled()
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run_1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(router.currentRoute.value.query.runId).toBe('run_1')
    expect(agentosApi.getAcgView).not.toHaveBeenCalled()
    expect(wrapper.findComponent(WorkflowProgressBar).exists()).toBe(true)
    const inspector = wrapper.findComponent({ name: 'AcgRunInspector' })
    expect(inspector.exists()).toBe(true)
    expect(inspector.props('runId')).toBe('run_1')
    expect(inspector.props('progress')).toEqual(expect.objectContaining({ runId: 'run_1' }))
    wrapper.unmount()
  })

  it('keeps Chat streaming independent from Workflow planning', async () => {
    chatStoreMock.loading = true
    chatStoreMock.isStreaming = true
    const { wrapper } = await mountPage()
    await setInputAndUpgrade(wrapper, '流式聊天期间启动')

    expect(chatStoreMock.startAgentRun).toHaveBeenCalledOnce()
    expect(chatStoreMock.isStreaming).toBe(true)
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledWith('run_1', expect.any(Object))
    wrapper.unmount()
  })

  it('starts a clean Agent draft without restoring the previous history Run', async () => {
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'run_history', 'completed')]
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress({
      runId: 'run_history',
      taskId: 'task_run_history',
      status: 'completed',
      phase: 'completed'
    }))
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue(run('run_history'))
    vi.mocked(agentosApi.getAcgView).mockResolvedValue(acg('run_history'))

    const { wrapper, router } = await mountPage('?workspace=agent&contextId=conversation_1&runId=run_history')
    await flushPromises()
    const previousDraftId = localStorage.getItem('chat.workflow_draft_conversation_id')

    expect(wrapper.find('.workflow-history-detail').exists()).toBe(true)
    window.dispatchEvent(new Event('agent-new-task'))
    await flushPromises()

    expect(router.currentRoute.value.query).toEqual({ workspace: 'agent' })
    expect(wrapper.find('.workflow-history-detail').exists()).toBe(false)
    expect(wrapper.get('.chat-panel').classes()).toContain('hero-mode')
    expect(localStorage.getItem('chat.workflow_draft_conversation_id')).not.toBe(previousDraftId)
    expect(chatStoreMock.startAgentRun).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows idempotency conflict without falling back to synchronous start', async () => {
    chatStoreMock.startAgentRun.mockRejectedValue({ isAxiosError: true, response: { status: 409 } })
    const { wrapper } = await mountPage()
    await setInputAndUpgrade(wrapper)

    expect(wrapper.text()).toContain('本次提交发生冲突，已保留原身份')
    expect(workflowApi.startWorkflow).not.toHaveBeenCalled()
    expect(workflowApi.getWorkflowProgress).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('delegates identity management to the Store when a temporarily unavailable submission is retried', async () => {
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
    expect(secondRequestId).toBeUndefined()
    expect(firstRequestId).toBeUndefined()
    expect(chatStoreMock.startAgentRun).toHaveBeenCalledTimes(2)
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

    expect(wrapper.get('.workflow-history-detail').text()).toContain('任务原文不属于运行状态')
    const artifactPanel = wrapper.findComponent({ name: 'GenericArtifactPanel' })
    expect(artifactPanel.props('stepOutputs')).toHaveLength(0)
    expect(artifactPanel.props('finalArtifacts')).toEqual([
      expect.objectContaining({ artifactId: 'legacy_projection', content: '# Legacy report' })
    ])
    expect(chatStoreMock.messages).toHaveLength(0)
    wrapper.unmount()
  })

  it('ends the loading state and retries after both history detail requests fail', async () => {
    vi.mocked(agentosApi.getWorkflowRun).mockRejectedValue(new Error('detail unavailable'))
    vi.mocked(agentosApi.getAcgView).mockRejectedValue(new Error('projection unavailable'))
    vi.mocked(workflowApi.getWorkflowProgress).mockResolvedValue(progress({
      runId: 'run_retry',
      taskId: 'task_run_retry',
      status: 'completed',
      phase: 'completed'
    }))

    const { wrapper } = await mountPage('?workspace=agent&runId=run_retry')
    await flushPromises()

    expect(wrapper.get('.workflow-history-loading').text()).toContain('任务详情暂时未能加载')
    expect(wrapper.text()).not.toContain('正在恢复任务详情')

    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue(run('run_retry'))
    vi.mocked(agentosApi.getAcgView).mockResolvedValue(acg('run_retry'))
    await wrapper.get('.workflow-history-loading button').trigger('click')
    await flushPromises()

    expect(wrapper.find('.workflow-history-loading').exists()).toBe(false)
    expect(wrapper.findComponent({ name: 'GenericArtifactPanel' }).exists()).toBe(true)
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

  const dispatchRun = (): WorkflowRun => ({ ...run(), status: 'pending', runtimeRevision: 7,
    actionCapabilities: capabilitiesFixture('run_1', 'mission_run_1', 'pending', 7,
      { canExecuteFormalAction: true, formalActions: ['dispatch'] }),
    formalControl: { status: 'ACTIVATED', permitStatus: 'ISSUED', permitId: 'permit',
      dispatchEnabled: true, dispatchEligible: true, graphId: 'graph', graphVersion: 1 } })
  const dispatchPage = async () => {
    chatStoreMock.workflowBindings.conversation_1 = [binding('conversation_1', 'run_1')]
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue(dispatchRun())
    return mountPage('?workspace=chat&contextId=conversation_1&runId=run_1&missionId=mission_run_1')
  }
  const clickDispatch = async (wrapper: VueWrapper) => {
    await wrapper.get('.formal-control__primary').trigger('click'); await flushPromises()
  }
  it.each(['pending', 'running'] as const)('does not infer a handoff from Permit/eligibility or status %s', async status => {
    const page = await dispatchPage()
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue({ ...dispatchRun(), status })
    await page.wrapper.get('.formal-control header button').trigger('click'); await flushPromises()
    expect(page.wrapper.text()).not.toContain('是否切换到 Workbench')
    expect(page.router.currentRoute.value.path).toBe('/chat'); page.wrapper.unmount()
  })
  it.each(['ACCEPTED', 'IDEMPOTENT_REPLAY'])('offers an optional verified handoff after %s, once per Dispatch', async status => {
    const post = vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(async (_m, _r, _a, command) =>
      ({ operationId: command.operationId, status, dispatchId: 'dispatch-1' }))
    const { wrapper, router } = await dispatchPage()
    await clickDispatch(wrapper)
    expect(wrapper.text()).toContain('是否切换到 Workbench')
    expect(router.currentRoute.value.path).toBe('/chat')
    await wrapper.findAll('button').find(b => b.text() === '稍后')!.trigger('click')
    expect(router.currentRoute.value.path).toBe('/chat')
    expect(wrapper.text()).not.toContain('是否切换到 Workbench')
    expect(wrapper.text()).toContain('打开所选 Run 的 Workbench')
    wrapper.unmount()
    const reopened = await dispatchPage(); expect(reopened.wrapper.text()).toContain('打开所选 Run 的 Workbench')
    expect(post).toHaveBeenCalledTimes(1)
    await clickDispatch(reopened.wrapper)
    expect(reopened.wrapper.text()).not.toContain('是否切换到 Workbench')
    expect(post).toHaveBeenCalledTimes(2) // Explicit replay click, never refresh/remount dispatch.
    expect(post.mock.calls[0][3]).toEqual(post.mock.calls[1][3]); reopened.wrapper.unmount()
  })
  it.each([false, true])('validates backend ownership before entering Workbench (wrong owner=%s)', async wrong => {
    vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(async (_m, _r, _a, command) =>
      ({ operationId: command.operationId, status: 'ACCEPTED', dispatchId: 'dispatch-2' }))
    const { wrapper, router } = await dispatchPage()
    router.addRoute({ path: '/agentos/missions/:missionId/workspace', component: { template: '<div />' } })
    chatStoreMock.messages.push({ id: 'kept', role: 'user', content: 'original conversation' })
    await clickDispatch(wrapper)
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue({ ...dispatchRun(), missionId: wrong ? 'foreign' : 'mission_run_1' })
    await wrapper.findAll('button').find(b => b.text() === '进入 Workbench')!.trigger('click'); await flushPromises()
    expect(router.currentRoute.value.path).toBe(wrong ? '/chat' : '/agentos/missions/mission_run_1/workspace')
    if (wrong) expect(wrapper.text()).toContain('无法验证')
    else expect(router.currentRoute.value.query.runId).toBe('run_1')
    expect(chatStoreMock.messages[0].content).toBe('original conversation'); wrapper.unmount()
  })
  it('never shows an obsolete Conversation Dispatch receipt in a newly selected Conversation', async () => {
    let finish!: (value: any) => void
    const post = vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const { wrapper, router } = await dispatchPage()
    await wrapper.get('.formal-control__primary').trigger('click')
    await router.push('/chat?workspace=chat&contextId=conversation_B'); await flushPromises()
    finish({ operationId: post.mock.calls[0][3].operationId, status: 'ACCEPTED', dispatchId: 'late' }); await flushPromises()
    expect(wrapper.text()).not.toContain('是否切换到 Workbench')
    expect(router.currentRoute.value.query.contextId).toBe('conversation_B'); wrapper.unmount()
  })
})
