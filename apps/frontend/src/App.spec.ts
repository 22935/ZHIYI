import { flushPromises, mount } from '@vue/test-utils'
import { reactive, defineComponent, h, inject } from 'vue'
import WorkspaceModeSwitch from '@/components/workspace/WorkspaceModeSwitch.vue'
import { workspaceShellKey, type WorkspaceSurface } from '@/features/workspace/shell'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import { agentosApi } from '@/services/api/agentos'
import { conversationApi } from '@/services/api/conversation'
import { workflowApi } from '@/services/api/workflow'

const clearMessages = vi.fn()
const bootstrap = vi.fn()
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
const chatStoreState = reactive({
  workflowBindings: {} as Record<string, any[]>,
  messages: [] as Array<Record<string, unknown>>,
  contextId: null as string | null,
  conversationWorkspaceMode: null as 'agent' | 'chat' | null,
  contextUsedTokens: null as number | null,
  contextWindowTokens: null as number | null,
  contextModel: null as string | null,
  contextModels: {} as Record<string, number>,
  isStreaming: false,
  isLoadingConversation: false,
  clearMessages,
  fetchContextWindows: vi.fn(async () => {}),
  getActiveWorkflowBinding: vi.fn((id: string) => [...(chatStoreState.workflowBindings[id] || [])].reverse().find(item => !item.invalidAt)),
  getLatestWorkflowBinding: vi.fn((id: string) => [...(chatStoreState.workflowBindings[id] || [])].reverse()[0]),
  pendingMissionLaunch: vi.fn(() => null),
  resumeMissionLaunch: vi.fn(),
  migrateDraftBindings: vi.fn(),
  loadHistory: vi.fn(async (id: string) => { chatStoreState.contextId = id }),
  updateWorkflowBindingStatus: vi.fn(),
  markWorkflowBindingInvalid: vi.fn(),
  startAgentRun: vi.fn(),
  upgradeToWorkflow: vi.fn(),
  sendMessage: vi.fn(),
  sendMessageStream: vi.fn()
})
clearMessages.mockImplementation(() => {
  chatStoreState.messages = []
  chatStoreState.contextId = null
})
const useChatStore = vi.fn(() => chatStoreState)

vi.mock('@/stores/chat', () => ({
  useChatStore
}))

vi.mock('@/stores/workflowRuns', () => ({
  useWorkflowRunsStore: () => ({ bootstrap })
}))

vi.mock('@/stores/user', () => ({
  useUserStore: () => ({
    currentUser: null,
    loadCurrentUser: vi.fn(),
    setCurrentUser: vi.fn()
  })
}))


vi.mock('@/services/api/conversation', () => ({
  conversationApi: {
    getUserConversations: vi.fn().mockResolvedValue([]),
    deleteConversation: vi.fn(),
    getConversation: vi.fn(async (contextId: string) => ({ id: contextId, contextId, workspaceMode: 'chat' }))
  }
}))

vi.mock('@/services/api/agentos', () => ({
  agentosApi: {
    listMissions: vi.fn(),
    getWorkflowRun: vi.fn(async (runId: string) => ({
      runId, missionId: 'mission-old', workflowId: 'workflow', domain: 'general', status: 'completed',
      steps: [], input: {}, output: {}, checkpoints: [], trace: []
    })),
    getAcgView: vi.fn(async (runId: string) => ({
      runId, status: 'completed', engine: 'acg', completedStepIds: [], activeStepIds: [], stepStates: [],
      provenance: { productions: [], consumptions: [], interactions: [] }, interactions: [], contractViolations: [],
      recoveryTrace: [], scheduleTrace: [], deliverables: [], finalReport: null,
      lowEntropyMetrics: { averageSavingRatio: 0, effectiveSavingRatio: 0, tokensAvailable: 0, tokensDelivered: 0,
        tokensSaved: 0, recoveryCount: 0, interactionCount: 0, contractViolationCount: 0, integrityStatus: 'valid' }
    }))
  }
}))

vi.mock('@/services/api/workflow', () => ({
  workflowApi: {
    listRuns: vi.fn(),
    getWorkflowProgress: vi.fn(async (runId: string) => ({
      taskId: `task_${runId}`, runId, workflowId: 'workflow', status: 'completed', phase: 'completed',
      message: '', percent: 100, totalSteps: 0, pendingSteps: 0, runningSteps: 0, waitingReviewSteps: 0,
      retryingSteps: 0, failedSteps: 0, completedSteps: 0, cancelledSteps: 0, currentStepId: null,
      activeStepIds: [], completedStepIds: [], startedAt: null, updatedAt: null, progress: 100, percentage: 100
    }))
  }
}))

const passthrough = { template: '<div><slot /></div>' }
const iconStub = { template: '<span><slot /></span>' }

describe('Workbench / OScode shell', () => {
  beforeEach(() => {
    localStorage.clear()
    chatStoreState.workflowBindings = {}
    chatStoreState.messages = []
    chatStoreState.contextId = null
    clearMessages.mockClear()
    localStorage.setItem('layout.workspace_mode', 'agent')
    localStorage.setItem('layout.chat_nav_open', '1')
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })
    })
    vi.mocked(workflowApi.listRuns).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 100 })
  })

  afterEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('keeps the ACG hub free of the history side panel; projects live only in the center', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', component: { template: '<div />' } },
        { path: '/history', component: { template: '<div />' } },
        { path: '/agentos/acg', component: { template: '<div />' } },
        { path: '/agentos/missions/:missionId/workspace', component: { template: '<div />' } }
      ]
    })
    await router.push('/agentos/acg')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router],
        mocks: { $t: (key: string) => key },
        stubs: {
          AppTopBar: passthrough,
          DesktopRuntimeStatus: passthrough,
          UserAvatar: passthrough,
          ErrorBoundary: passthrough,
          'el-container': passthrough,
          'el-aside': passthrough,
          'el-main': passthrough,
          'el-menu': passthrough,
          'el-menu-item': passthrough,
          'el-drawer': passthrough,
          'el-alert': passthrough,
          'el-icon': iconStub
        }
      }
    })
    await vi.dynamicImportSettled()
    await flushPromises()

    // hub 不再弹出历史子栏，也不再为子栏拉取工程项目
    expect(wrapper.find('#chat-side-panel').exists()).toBe(false)
    expect(wrapper.find('.chat-project-count').exists()).toBe(false)
    expect(wrapper.find('.chat-project-row').exists()).toBe(false)
    expect(agentosApi.listMissions).not.toHaveBeenCalled()
    expect(workflowApi.listRuns).not.toHaveBeenCalled()
    expect(wrapper.find('.sidebar-nav [index="/settings"]').exists()).toBe(false)
    expect(wrapper.find('.primary-sidebar .sidebar-settings-menu [index="/settings"]').exists()).toBe(true)
    const sidebarFooter = wrapper.find('.primary-sidebar .sidebar-footer')
    expect(sidebarFooter.find('.user-profile').element.compareDocumentPosition(sidebarFooter.find('.sidebar-settings-menu').element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(wrapper.text()).not.toContain('ACG 历史记录')
    expect(wrapper.text()).not.toContain('联邦管理')
    expect(wrapper.text()).not.toContain('模型管理')
    expect(wrapper.text()).not.toContain('nav.roles')

    wrapper.unmount()
  })

  it('routes the chat panel history shortcut to the chat history tab', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', component: { template: '<div />' } },
        { path: '/history', component: { template: '<div />' } },
        { path: '/agentos/acg', component: { template: '<div />' } }
      ]
    })
    await router.push('/chat?workspace=chat')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router],
        mocks: { $t: (key: string) => key },
        stubs: {
          AppTopBar: passthrough,
          DesktopRuntimeStatus: passthrough,
          UserAvatar: passthrough,
          ErrorBoundary: passthrough,
          'el-container': passthrough,
          'el-aside': passthrough,
          'el-main': passthrough,
          'el-menu': passthrough,
          'el-menu-item': passthrough,
          'el-drawer': passthrough,
          'el-alert': passthrough,
          'el-icon': iconStub
        }
      }
    })
    await vi.dynamicImportSettled()
    await flushPromises()

    expect(wrapper.find('#chat-side-panel').exists()).toBe(true)
    await wrapper.find('.history-action').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/history')
    expect(router.currentRoute.value.query).toMatchObject({ workspace: 'chat' })

    wrapper.unmount()
  })

  it.each(['chat', 'agent'] as const)('Shell starts a fresh %s conversation without clearing chat state itself', async mode => {
    localStorage.setItem('layout.workspace_mode', mode)
    localStorage.setItem('layout.chat_nav_open', '1')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', component: { template: '<div />' } },
        { path: '/history', component: { template: '<div />' } },
        { path: '/agentos/acg', component: { template: '<div />' } }
      ]
    })
    await router.push(`/history?workspace=${mode}`)
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router],
        mocks: { $t: (key: string) => key },
        stubs: {
          AppTopBar: passthrough,
          DesktopRuntimeStatus: passthrough,
          UserAvatar: passthrough,
          ErrorBoundary: passthrough,
          'el-container': passthrough,
          'el-aside': passthrough,
          'el-main': passthrough,
          'el-menu': passthrough,
          'el-menu-item': passthrough,
          'el-drawer': passthrough,
          'el-alert': passthrough,
          'el-icon': iconStub
        }
      }
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    clearMessages.mockClear()

    await wrapper.find('.primary-sidebar .chat-nav-trigger').trigger('click')
    await flushPromises()
    expect(wrapper.find('.new-chat-action').exists()).toBe(true)
    await wrapper.find('.new-chat-action').trigger('click')
    await flushPromises()

    expect(router.currentRoute.value.path).toBe('/chat')
    expect(router.currentRoute.value.query).toEqual({ workspace: 'chat', newConversation: '1' })
    expect(clearMessages).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('switches Workbench and OScode without clearing the conversation, while activity buttons only switch the left view', async () => {
    localStorage.setItem('layout.workspace_mode', 'agent')
    localStorage.setItem('layout.chat_nav_open', '1')
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', component: { template: '<div />' } },
        { path: '/history', component: { template: '<div />' } },
        { path: '/agentos/acg', component: { template: '<div />' } }
      ]
    })
    chatStoreState.contextId = 'old-context'
    chatStoreState.messages = [{ id: 'preserved', role: 'user', content: '保留当前对话' }]
    chatStoreState.workflowBindings = { 'old-context': [{
      conversationId: 'old-context', missionId: 'mission-old', runId: 'old-run',
      source: 'chat', status: 'completed', createdAt: '2026-11-05'
    }] }
    router.addRoute({ path: '/agentos/missions/:missionId/workspace', component: defineComponent({
      setup() {
        const shell = inject(workspaceShellKey)!
        return () => h(WorkspaceModeSwitch, { active: 'workbench', onSelect: (surface: WorkspaceSurface) => shell.switchSurface(surface) })
      }
    }) })
    await router.push('/chat?workspace=agent&contextId=old-context&runId=old-run')
    await router.isReady()
    const wrapper = mount(App, {
      global: {
        plugins: [router],
        mocks: { $t: (key: string) => key },
        stubs: {
          AppTopBar: passthrough, DesktopRuntimeStatus: passthrough, UserAvatar: passthrough,
          ErrorBoundary: passthrough, 'el-container': passthrough, 'el-aside': passthrough,
          'el-main': passthrough, 'el-menu': passthrough, 'el-menu-item': passthrough,
          'el-drawer': passthrough, 'el-alert': passthrough, 'el-icon': iconStub
        }
      }
    })
    await vi.dynamicImportSettled(); await flushPromises(); clearMessages.mockClear()
    await wrapper.find('.workspace-switch-btn[aria-selected="false"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/agentos/missions/mission-old/workspace')
    expect(router.currentRoute.value.query).toEqual({ runId: 'old-run' })
    const workbenchPath = router.currentRoute.value.fullPath
    for (const button of wrapper.findAll('.workbench-activity-button')) await button.trigger('click')
    expect(wrapper.findAll('.workbench-activity-button')).toHaveLength(4)
    expect(router.currentRoute.value.fullPath).toBe(workbenchPath)
    expect(wrapper.get('[aria-label="思维链"]').attributes('aria-pressed')).toBe('true')
    await wrapper.find('.workspace-switch-btn[aria-selected="false"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/chat')
    expect(router.currentRoute.value.query.contextId).toBe('old-context')
    expect(chatStoreState.messages[0].content).toBe('保留当前对话')
    expect(clearMessages).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it.each(['chat', 'agent'] as const)('runs the %s Shell new-chat intent through the actual ChatView and allocates an isolated draft', async (mode) => {
    const { default: ChatView } = await import('@/views/ChatView.vue')
    localStorage.setItem('layout.workspace_mode', mode)
    localStorage.setItem('layout.chat_nav_open', '1')
    localStorage.setItem('chat.workflow_draft_conversation_id', 'draft:old')
    chatStoreState.contextId = 'ctx-old'
    chatStoreState.messages = [{ id: 'old-message', role: 'assistant', content: 'old' }]
    const oldBinding = {
      conversationId: 'ctx-old', missionId: 'mission-old', runId: 'run-old',
      status: 'completed', source: 'chat', createdAt: '2026-10-31T00:00:00Z',
      clientRequestId: 'request-old', acgTaskId: 'run-old', conversationAliases: ['draft:old']
    }
    chatStoreState.workflowBindings = { 'ctx-old': [oldBinding] }
    vi.stubGlobal('ResizeObserver', class { observe() {}; disconnect() {} })
    HTMLElement.prototype.scrollTo = vi.fn()
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', component: ChatView },
        { path: '/history', component: { template: '<div />' } },
        { path: '/agentos/acg', component: { template: '<div />' } }
      ]
    })
    await router.push(`/chat?workspace=${mode}&contextId=ctx-old&runId=run-old`)
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router],
        mocks: { $t: (key: string) => key },
        stubs: {
          AppTopBar: passthrough, DesktopRuntimeStatus: passthrough, UserAvatar: passthrough,
          ErrorBoundary: passthrough, 'el-container': passthrough, 'el-aside': passthrough,
          'el-main': passthrough, 'el-menu': passthrough, 'el-menu-item': passthrough,
          'el-drawer': passthrough, 'el-alert': passthrough, 'el-icon': iconStub,
          PermissionSelector: false, AcgRunInspector: true, GenericArtifactPanel: true,
          WorkflowProgressBar: true, MessageBubble: true, ModelRuntimeControls: true,
          NativeWorkspacePicker: true, AgentOsRunSummaryCard: true, RuntimeAuditTimeline: true,
          FileManager: true, WorkflowReviewPanel: true, 'el-button': true, 'el-input': true,
          'el-dialog': true, 'el-select': true, 'el-option': true,
          'el-tag': true, 'el-collapse': true, 'el-collapse-item': true, 'el-avatar': true
        }
      }
    })
    await vi.dynamicImportSettled(); await flushPromises()
    clearMessages.mockClear()
    expect(wrapper.find('.new-chat-action').exists()).toBe(true)
    await wrapper.find('.new-chat-action').trigger('click')
    await vi.dynamicImportSettled(); await flushPromises()

    const nextDraft = localStorage.getItem('chat.workflow_draft_conversation_id')
    expect(nextDraft).toMatch(/^draft:/)
    expect(nextDraft).not.toBe('draft:old')
    expect(clearMessages).toHaveBeenCalledTimes(1)
    expect(chatStoreState.messages).toEqual([])
    expect(chatStoreState.workflowBindings['ctx-old']).toEqual([oldBinding])
    expect(router.currentRoute.value.query).toEqual({ workspace: 'chat' })
    expect(chatStoreState.getActiveWorkflowBinding(nextDraft!)).toBeUndefined()
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('exposes edit and delete actions for Chat conversations', async () => {
    localStorage.setItem('layout.workspace_mode', 'chat')
    vi.mocked(conversationApi.getUserConversations).mockResolvedValue([{
      id: 'conversation_1', userId: 'user_1', contextId: 'context_1', title: '项目讨论',
      workspaceMode: 'chat', createdAt: '2026-09-05T00:00:00Z', updatedAt: '2026-09-06T00:00:00Z'
    }])
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/chat', component: { template: '<div />' } },
        { path: '/history', component: { template: '<div />' } },
        { path: '/agentos/acg', component: { template: '<div />' } }
      ]
    })
    await router.push('/chat?workspace=chat')
    await router.isReady()

    const wrapper = mount(App, {
      global: {
        plugins: [router],
        mocks: { $t: (key: string) => key },
        stubs: {
          AppTopBar: passthrough,
          DesktopRuntimeStatus: passthrough,
          UserAvatar: passthrough,
          ErrorBoundary: passthrough,
          'el-container': passthrough,
          'el-aside': passthrough,
          'el-main': passthrough,
          'el-menu': passthrough,
          'el-menu-item': passthrough,
          'el-drawer': passthrough,
          'el-alert': passthrough,
          'el-icon': iconStub
        }
      }
    })
    await vi.dynamicImportSettled()
    await flushPromises()

    expect(wrapper.findAll('.chat-project-action')).toHaveLength(2)
    expect(wrapper.find('.chat-project-action--edit').exists()).toBe(true)
    expect(wrapper.find('.chat-project-action--delete').exists()).toBe(true)
    expect(wrapper.find('.chat-project-action--open').exists()).toBe(false)

    await wrapper.find('.chat-project-row').trigger('contextmenu', { clientX: 120, clientY: 160 })
    await flushPromises()
    const menu = document.body.querySelector('.sidebar-action-menu')
    expect(menu?.textContent).toContain('编辑标题')
    expect(menu?.textContent).toContain('删除对话')

    wrapper.unmount()
  })
})
