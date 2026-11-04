import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, ref } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AuthenticatedAppShell from './AuthenticatedAppShell.vue'
import ChatView from '@/views/ChatView.vue'
import MissionWorkspaceView from '@/views/MissionWorkspaceView.vue'
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import { useChatStore } from '@/stores/chat'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { agentosApi } from '@/services/api/agentos'
import { conversationApi } from '@/services/api/conversation'
import { chatApi } from '@/services/api/chat'
import { workflowApi } from '@/services/api/workflow'
import { agentosRequest } from '@/services/api/agentos/client'
import { TextDocument, workspaceDocuments } from '@/workbench/core/documents'
import { requestOpenFile, resetOpenFile } from '@/workbench/core/openFileRequest'
import { capabilitiesFixture } from '@/test/fixtures/runCapabilities'

const observations = vi.hoisted(() => ({ instances: [] as any[] }))
vi.mock('@/workbench/runtime/observation', async original => ({
  ...await original<any>(),
  RuntimeObservationAdapter: class {
    start = vi.fn(); stop = vi.fn()
    constructor() { observations.instances.push(this) }
  }
}))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/stores/user', () => ({ useUserStore: () => ({ currentUser: null, loadCurrentUser: vi.fn() }) }))

const passthrough = { template: '<div><slot /></div>' }
const button = { props: ['disabled'], emits: ['click'], template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>' }
const input = { props: ['modelValue'], emits: ['update:modelValue'], template: '<textarea :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' }
const graph = defineComponent({
  emits: ['selectSemanticTask'], setup() { return { zoom: ref(1) } },
  template: '<div class="test-graph"><button class="zoom" @click="zoom++">{{ zoom }}</button><button class="pick-task" @click="$emit(\'selectSemanticTask\', \'task\')">pick</button></div>'
})
const graphEntry = { entryId: 'graph', kind: 'graph', name: 'graph.acg', group: 'overview', displayOrder: 0 }
const taskEntry = { entryId: 'task', kind: 'task', name: 'task', group: 'steps', displayOrder: 1, semanticTaskKey: 'task', acgNodeId: 'node' }
const artifactEntry = { entryId: 'artifact', kind: 'artifact', name: 'artifact.md', group: 'output', displayOrder: 2, semanticTaskKey: 'task', artifactId: 'artifact-id', contentRef: 'manifest', identityQuality: 'canonical' }
const projection = (missionId = 'mission', runId = 'run', newest = 'run'): any => ({
  mission: { missionId, userId: 'user', goal: 'Goal', status: 'created', createdAt: '1', updatedAt: '1', metadata: {} },
  activeRun: { runId, status: 'running', createdAt: '1', isActive: runId === newest },
  runs: [{ runId: 'run', status: newest === 'run' ? 'running' : 'completed', createdAt: '1', isActive: newest === 'run' },
    ...(newest !== 'run' ? [{ runId: newest, status: 'running', createdAt: '2', isActive: true }] : [])],
  activeGraph: { graphId: 'graph', nodes: [{ nodeId: 'node', nodeType: 'step', name: 'Task' }], edges: [] },
  graphNodes: [{ acgNodeId: 'node', semanticTaskKey: 'task', name: 'Task', nodeType: 'step', displayOrder: 0 }],
  entries: [graphEntry, taskEntry, artifactEntry], diagnostics: []
})
const binding = (conversationId = 'ctx') => ({
  conversationId, conversationAliases: ['draft:original'], missionId: 'mission', runId: 'run', acgTaskId: 'run',
  status: 'running', source: 'chat' as const, clientRequestId: 'operation', createdAt: '1'
})
const channel = (contextId: string) => {
  let writer!: ReadableStreamDefaultController<Uint8Array>
  return {
    response: new Response(new ReadableStream<Uint8Array>({ start(c) { writer = c } }), { headers: { 'X-Chat-Context-Id': contextId } }),
    send: (event: string, data: object) => writer.enqueue(new TextEncoder().encode(
      `data:${JSON.stringify({ event, data, requestId: 'message-request' })}\n\n`)),
    close: () => writer.close()
  }
}
let wrapper: VueWrapper | undefined
let chatTransport: Promise<Response> | undefined
let activeStreams = 0, maximumStreams = 0
let runtimeWriter: ReadableStreamDefaultController<Uint8Array>
let newestRun = 'run'
const settle = async () => { await flushPromises(); await vi.dynamicImportSettled(); await flushPromises() }
const deferred = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}
const state = () => wrapper!.findComponent(MissionWorkspaceView).vm as any
const mountShell = async (url = '/chat?workspace=chat&contextId=ctx&missionId=mission&runId=run', initialContext: string | null = 'ctx') => {
  const pinia = createPinia(); setActivePinia(pinia)
  vi.spyOn(useWorkflowRunsStore(), 'bootstrap').mockResolvedValue(undefined)
  const chat = useChatStore()
  chat.contextId = initialContext; chat.setRole('original-role')
  chat.addMessage({ id: 'message', role: 'user', content: 'original', fileUrl: '/file-reference' })
  chat.addWorkflowBinding(binding(initialContext || 'draft:original'))
  const clear = vi.spyOn(chat, 'clearMessages')
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/chat', component: ChatView },
    { path: '/agentos/missions/:missionId/workspace', component: MissionWorkspaceView },
    { path: '/history', component: { template: '<div class="history">history</div>' } },
    { path: '/agentos/acg', component: { template: '<div>ACG</div>' } }
  ] })
  await router.push(url); await router.isReady()
  wrapper = mount(AuthenticatedAppShell, { global: {
    plugins: [pinia, router], mocks: { $t: (key: string) => key }, stubs: {
      AppTopBar: passthrough, DesktopRuntimeStatus: passthrough, UserAvatar: passthrough,
      'el-container': passthrough, 'el-aside': passthrough, 'el-main': passthrough,
      'el-menu': passthrough, 'el-menu-item': passthrough, 'el-drawer': passthrough,
      'el-button': button, 'el-input': input, 'el-icon': passthrough, 'el-dialog': true,
      'el-select': true, 'el-option': true, 'el-tag': true, 'el-collapse': true, 'el-collapse-item': true,
      PermissionSelector: true, AcgRunInspector: true, GenericArtifactPanel: true,
      WorkflowProgressBar: true, ModelRuntimeControls: true, NativeWorkspacePicker: true,
      AgentOsRunSummaryCard: true, RuntimeAuditTimeline: true, FileManager: true, WorkflowReviewPanel: true,
      MessageBubble: { props: ['message'], template: '<p class="test-message" :data-file="message.fileUrl">{{ message.content }}</p>' },
      GraphEditor: graph, TaskEditor: { template: '<div>Task</div>' },
      ArtifactEditor: { template: '<div>Artifact</div>' }, RunProgressEditor: { template: '<div>Progress</div>' },
      WorkbenchContributionRenderer: true, TaskRelatedFilesInspector: true,
      WorkbenchAuxiliarySidebar: { props: ['view'], template: '<div class="test-auxiliary" :data-view="view.id" />' },
      WorkspaceCodeEditor: { props: ['document'], emits: ['cursor'], template: '<textarea class="file-buffer" :value="document.getText()" @input="document.applyEdits([{ from: 0, to: document.getText().length, insert: $event.target.value }]); $emit(\'cursor\', { line: 2, column: 3 })" />' }
    }
  } })
  await settle()
  return { router, chat, clear }
}
const toWorkbench = async () => { await wrapper!.get('.primary-sidebar .acg-nav-group .chat-nav-trigger').trigger('click'); await settle() }
const toChat = async () => { await wrapper!.get('.primary-sidebar .chat-nav-group:not(.acg-nav-group) .chat-nav-trigger').trigger('click'); await settle() }

describe('PR-UI-02B actual Shell / Chat / Workbench continuity', () => {
  it('05A: dispatch handoff keeps the same Conversation and Run through the actual Shell', async () => {
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue({ runId: 'run', missionId: 'mission', workflowId: 'workflow',
      status: 'pending', runtimeRevision: 7, steps: [],
      actionCapabilities: capabilitiesFixture('run', 'mission', 'pending', 7, { canExecuteFormalAction: true, formalActions: ['dispatch'] }),
      formalControl: { status: 'ACTIVATED', permitStatus: 'ISSUED', permitId: 'permit', graphId: 'graph', graphVersion: 1,
        dispatchEnabled: true, dispatchEligible: true } } as any)
    const dispatch = vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(async (_m, _r, _a, command) =>
      ({ operationId: command.operationId, status: 'ACCEPTED', dispatchId: 'dispatch-shell' }))
    const { router, chat, clear } = await mountShell()
    const chatInstance = wrapper!.findComponent(ChatView).vm.$.uid
    await wrapper!.get('.formal-control__primary').trigger('click'); await settle()
    expect(router.currentRoute.value.path).toBe('/chat')
    expect(wrapper!.text()).toContain('是否切换到 Workbench')
    await wrapper!.findAll('button').find(b => b.text() === '进入 Workbench')!.trigger('click'); await settle()
    expect(router.currentRoute.value.path).toBe('/agentos/missions/mission/workspace')
    expect(router.currentRoute.value.query.runId).toBe('run')
    expect(wrapper!.findComponent(MissionWorkspaceView).exists()).toBe(true)
    await toChat()
    expect(wrapper!.findComponent(ChatView).vm.$.uid).toBe(chatInstance)
    expect(chat.messages[0].content).toBe('original'); expect(chat.contextId).toBe('ctx')
    expect(clear).not.toHaveBeenCalled(); expect(dispatch).toHaveBeenCalledTimes(1)
    expect(maximumStreams).toBeLessThanOrEqual(1)
  })

  it.each(['running', 'waiting_review', 'completed'])('05B: persistent entry restores %s and preserves state through repeated round trips', async status => {
    vi.mocked(agentosApi.getWorkflowRun).mockImplementation(async runId => ({ runId, missionId: 'mission', status, steps: [] } as any))
    const { router, chat, clear } = await mountShell()
    const uid = wrapper!.findComponent(ChatView).vm.$.uid
    const post = vi.spyOn(agentosApi, 'submitFormalControl')
    for (let cycle = 0; cycle < 3; cycle++) {
      await wrapper!.findAll('button').find(b => b.text() === '打开所选 Run 的 Workbench')!.trigger('click'); await settle()
      expect(router.currentRoute.value.query.runId).toBe('run')
      expect(wrapper!.findComponent(MissionWorkspaceView).exists()).toBe(true)
      await toChat()
      expect(wrapper!.findComponent(ChatView).vm.$.uid).toBe(uid)
      expect(chat.contextId).toBe('ctx'); expect(chat.messages[0].content).toBe('original')
    }
    expect(post).not.toHaveBeenCalled(); expect(clear).not.toHaveBeenCalled()
    expect(maximumStreams).toBeLessThanOrEqual(1)
  })
  it.each([403, 404, 409, 'network'])('05B: persistent navigation fails closed on %s', async failure => {
    const { router } = await mountShell()
    vi.mocked(agentosApi.getWorkflowRun).mockRejectedValue(new Error(String(failure)))
    await wrapper!.findAll('button').find(b => b.text() === '打开所选 Run 的 Workbench')!.trigger('click'); await settle()
    expect(router.currentRoute.value.path).toBe('/chat'); expect(wrapper!.text()).toContain('无法验证')
  })
  it('05B: pending navigation cannot follow a changed Conversation', async () => {
    const { router } = await mountShell()
    const pending = deferred<any>()
    vi.mocked(agentosApi.getWorkflowRun).mockReturnValue(pending.promise)
    await wrapper!.findAll('button').find(b => b.text() === '打开所选 Run 的 Workbench')!.trigger('click')
    await router.push('/chat?contextId=other&workspace=chat'); await settle()
    pending.resolve({ runId: 'run', missionId: 'mission', status: 'running' }); await settle()
    expect(router.currentRoute.value.path).toBe('/chat'); expect(router.currentRoute.value.query.contextId).toBe('other')
  })

  it('05B: explicit historical selection is never replaced by a newer active Run', async () => {
    const { router, chat } = await mountShell()
    chat.addWorkflowBinding({ ...binding(), runId: 'new', acgTaskId: 'new', createdAt: '2' })
    await settle()
    expect(wrapper!.get('select[aria-label="选择任务 Run"]').findAll('option')).toHaveLength(2)
    await wrapper!.get('select[aria-label="选择任务 Run"]').setValue('new'); await settle()
    expect(router.currentRoute.value.query.runId).toBe('new')
    await wrapper!.get('select[aria-label="选择任务 Run"]').setValue('run'); await settle()
    await wrapper!.findAll('button').find(b => b.text() === '打开所选 Run 的 Workbench')!.trigger('click'); await settle()
    expect(router.currentRoute.value.query.runId).toBe('run')
    expect(wrapper!.findComponent(MissionWorkspaceView).exists()).toBe(true)
  })
  beforeEach(() => {
    localStorage.clear(); sessionStorage.clear(); observations.instances = []; resetOpenFile(); workspaceDocuments.reset()
    localStorage.setItem('layout.workspace_mode', 'chat'); localStorage.setItem('layout.chat_nav_open', '1')
    localStorage.setItem('chat.workflow_draft_conversation_id', 'draft:original')
    activeStreams = 0; maximumStreams = 0; newestRun = 'run'; chatTransport = undefined
    vi.stubGlobal('ResizeObserver', class { observe() {}; disconnect() {} })
    Object.defineProperty(window, 'matchMedia', { configurable: true, value: vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })) })
    HTMLElement.prototype.scrollTo = vi.fn()
    vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 1600, height: 900, left: 0, top: 0, bottom: 900, right: 1600, x: 0, y: 0, toJSON() {} })
    vi.spyOn(agentosApi, 'getMissionWorkspace').mockImplementation(async (missionId, options) => projection(missionId, options?.runId || newestRun, newestRun))
    vi.spyOn(agentosApi, 'getWorkflowRun').mockImplementation(async runId => ({ runId, missionId: 'mission', workflowId: 'workflow', status: 'running', steps: [], input: {}, output: {}, trace: [], checkpoints: [] } as any))
    vi.spyOn(agentosApi, 'getAcgView').mockImplementation(async runId => ({ runId, status: 'running', engine: 'acg', completedStepIds: [], activeStepIds: [], stepStates: [], provenance: {}, interactions: [], contractViolations: [], recoveryTrace: [], scheduleTrace: [], deliverables: [], lowEntropyMetrics: {} } as any))
    vi.spyOn(workflowApi, 'getWorkflowProgress').mockImplementation(async runId => ({ runId, taskId: runId, status: 'completed', phase: 'completed', completedSteps: 0 } as any))
    vi.spyOn(agentosApi, 'listMissions').mockResolvedValue({ items: [], total: 0 } as any)
    vi.spyOn(agentosRequest, 'post').mockRejectedValue(new Error('Navigation must not issue a Mission command'))
    vi.spyOn(conversationApi, 'getUserConversations').mockResolvedValue([])
    vi.spyOn(conversationApi, 'getConversation').mockImplementation(async contextId => ({ contextId, roleId: 'original-role', workspaceMode: 'chat' } as any))
    vi.spyOn(chatApi, 'getHistory').mockResolvedValue([{ id: 'history', role: 'assistant', content: 'restored from history', fileUrl: '/history-file' }])
    vi.stubGlobal('fetch', vi.fn(async (url, init) => {
      if (String(url).includes('/chat/text/stream')) return chatTransport!
      if (String(url).includes('/events')) {
        activeStreams++; maximumStreams = Math.max(maximumStreams, activeStreams)
        return new Response(new ReadableStream({ start(controller) {
          runtimeWriter = controller
          init.signal.addEventListener('abort', () => { activeStreams--; controller.error(new DOMException('aborted', 'AbortError')) }, { once: true })
        } }), { headers: { 'Content-Type': 'text/event-stream' } })
      }
      return Response.json({ context_windows: {} })
    }))
  })
  afterEach(async () => { wrapper?.unmount(); wrapper = undefined; await flushPromises(); expect(activeStreams).toBe(0); expect(agentosRequest.post).not.toHaveBeenCalled(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); resetOpenFile(); workspaceDocuments.reset() })

  it('A: retains the actual Conversation instance, unsent text, messages, files, role and reading position', async () => {
    const model = JSON.stringify({ provider: 'system', selectedModel: 'chosen-model', models: ['chosen-model'], thinkingMode: 'standard' })
    localStorage.setItem('kinlin.model_settings', model)
    const { chat, router, clear } = await mountShell()
    const view = wrapper!.findComponent(ChatView).vm.$.uid
    const draft = localStorage.getItem('chat.workflow_draft_conversation_id')
    await wrapper!.get('.composer-card textarea').setValue('not sent yet')
    ;(wrapper!.get('.messages').element as HTMLElement).scrollTop = 173
    await toWorkbench()
    expect(router.currentRoute.value.path).toBe('/agentos/missions/mission/workspace')
    await toChat()
    expect(wrapper!.findComponent(ChatView).vm.$.uid).toBe(view)
    expect((wrapper!.get('.composer-card textarea').element as HTMLTextAreaElement).value).toBe('not sent yet')
    expect((wrapper!.get('.messages').element as HTMLElement).scrollTop).toBe(173)
    expect(chat.messages[0]).toMatchObject({ content: 'original', fileUrl: '/file-reference' })
    expect(chat.currentRoleId).toBe('original-role'); expect(chat.contextId).toBe('ctx')
    expect(clear).not.toHaveBeenCalled(); expect(chatApi.getHistory).not.toHaveBeenCalled()
    expect(localStorage.getItem('chat.workflow_draft_conversation_id')).toBe(draft)
    expect(localStorage.getItem('kinlin.model_settings')).toBe(model)
  })

  it('B: retains EditorGroup tabs, dirty document, cursor, selections, graph viewport, panels and layout', async () => {
    const doc = new TextDocument('file:continuity', 'saved', 'v1')
    vi.spyOn(workspaceDocuments, 'open').mockResolvedValue(doc)
    await mountShell('/agentos/missions/mission/workspace?runId=run')
    const workbench = state(), layout = wrapper!.findComponent(WorkbenchLayout).vm as any
    workbench.openEntry(graphEntry); workbench.openEntry(taskEntry); workbench.openEntry(artifactEntry)
    requestOpenFile({ missionId: 'mission', workspaceRoot: '/workspace', relativePath: 'test.txt', name: 'test.txt' })
    await settle(); await wrapper!.get('.file-buffer').setValue('dirty buffer\nsecond line')
    expect(doc.dirty).toBe(true)
    const cursor = workbench.activeEditorStatus.cursor
    workbench.openEntry(graphEntry); await settle()
    await wrapper!.get('.zoom').trigger('click'); await wrapper!.get('.pick-task').trigger('click')
    const auxiliary = wrapper!.findAll('.editor-auxiliary-trigger').find(item => item.attributes('title').includes('文件'))!
    await auxiliary.trigger('click')
    if (workbench.panelTabs.length > 1) workbench.panelActiveTab = workbench.panelTabs[1].id
    layout.handleResizeKeydown('left', new KeyboardEvent('keydown', { key: 'ArrowRight' }))
    layout.handleResizeKeydown('right', new KeyboardEvent('keydown', { key: 'ArrowLeft' }))
    layout.toggleRightPane()
    layout.toggleBottomPanelCollapsed()
    await settle()
    const editors = [...workbench.openEditors], active = workbench.activeEditorId
    const panel = workbench.panelActiveTab
    const auxiliaryId = workbench.activeAuxiliaryId
    const collapsed = layout.bottomPanelCollapsed
    const classes = wrapper!.get('.workbench-layout').classes()
    const layoutStyle = wrapper!.get('.workbench-layout').attributes('style')
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await toChat(); expect(confirm).not.toHaveBeenCalled()
    await toWorkbench()
    expect(state().$.uid).toBe(workbench.$.uid); expect(wrapper!.findComponent(WorkbenchLayout).vm.$.uid).toBe(layout.$.uid)
    expect(state().openEditors).toEqual(editors); expect(state().activeEditorId).toBe(active)
    expect(state().selectedSemanticTaskKey).toBe('task'); expect(state().selectedGraphNodeId).toBe('node')
    expect(wrapper!.get('.zoom').text()).toBe('2')
    expect(state().panelActiveTab).toBe(panel); expect(wrapper!.get('.workbench-layout').attributes('style')).toBe(layoutStyle)
    expect(state().activeAuxiliaryId).toBe(auxiliaryId)
    expect(wrapper!.get('.workbench-layout').classes()).toEqual(classes)
    expect(layout.bottomPanelCollapsed).toBe(collapsed)
    expect(doc.getText()).toBe('dirty buffer\nsecond line'); expect(doc.dirty).toBe(true)
    state().activeEditorId = editors.find(id => id.startsWith('local-file:')); await settle()
    expect((wrapper!.get('.file-buffer').element as HTMLTextAreaElement).value).toBe(doc.getText())
    expect(state().activeEditorStatus.cursor).toBe(cursor)
    expect(workspaceDocuments.open).toHaveBeenCalledTimes(1)
  })

  it('C: a delayed real SSE keeps its owner while hidden, migrates its Draft, and never starts a second request', async () => {
    let deliver!: (response: Response) => void
    chatTransport = new Promise(resolve => { deliver = resolve })
    const delayed = channel('ctx-from-stream')
    const { chat, router, clear } = await mountShell('/chat?workspace=chat&runId=run&missionId=mission', null)
    const view = wrapper!.findComponent(ChatView).vm.$.uid
    await wrapper!.get('.composer-card textarea').setValue('stream question')
    await wrapper!.get('.composer-send').trigger('click')
    await toWorkbench()
    deliver(delayed.response); delayed.send('content_delta', { delta: 'first ' }); await settle()
    expect(router.currentRoute.value.path).toContain('/workspace')
    expect(chat.contextId).toBe('ctx-from-stream')
    delayed.send('content_delta', { delta: 'second' }); delayed.send('done', { status: 'completed', contextId: 'ctx-from-stream' }); delayed.close()
    await settle(); await toChat()
    expect(wrapper!.findComponent(ChatView).vm.$.uid).toBe(view)
    expect(chat.messages.at(-1)?.content).toBe('first second')
    expect(router.currentRoute.value.query.contextId).toBe('ctx-from-stream')
    expect(chat.getLatestWorkflowBinding('ctx-from-stream')?.runId).toBe('run')
    expect(chat.getLatestWorkflowBinding('draft:original')?.conversationId).toBe('ctx-from-stream')
    const calls = vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes('/chat/text/stream'))
    expect(calls).toHaveLength(1); expect(calls[0][1]!.signal!.aborted).toBe(false)
    expect(chat.loading).toBe(false); expect(chat.isStreaming).toBe(false); expect(clear).not.toHaveBeenCalled()
  })

  it('D: retains one Runtime SSE and hidden deltas, pauses polling, and refreshes external Run facts', async () => {
    vi.useFakeTimers()
    await mountShell('/agentos/missions/mission/workspace?runId=run')
    const workbench = state(), adapter = observations.instances[0]
    workbench.openEntry(artifactEntry); await settle()
    const starts = adapter.start.mock.calls.length
    const runtime = workbench.runtimeStore
    const delta = (sequence: number, text: string) => runtimeWriter.enqueue(new TextEncoder().encode(
      `data:${JSON.stringify({ eventId: `e${sequence}`, eventType: 'planner.model.output.delta', runId: 'run', sequence, payload: { delta: text } })}\n\n`))
    delta(1, 'visible '); await settle()
    expect(activeStreams).toBe(1)
    await toChat(); expect(activeStreams).toBe(1)
    delta(2, 'hidden output'); await settle()
    expect(runtime.planning.outputBuffer).toBe('visible hidden output')
    const reads = vi.mocked(agentosApi.getMissionWorkspace).mock.calls.length
    await vi.advanceTimersByTimeAsync(20000); await settle()
    expect(agentosApi.getMissionWorkspace).toHaveBeenCalledTimes(reads)
    newestRun = 'external-new-run'
    await toWorkbench()
    expect(state().$.uid).toBe(workbench.$.uid); expect(observations.instances).toEqual([adapter])
    expect(adapter.start).toHaveBeenCalledTimes(starts + 1)
    expect(state().runtimeStore === runtime).toBe(true)
    expect(state().runtimeStore.planning.outputBuffer).toBe('visible hidden output')
    expect(state().selectedRunId).toBe('run'); expect(state().lifecycle.latestRunId).toBe('external-new-run')
    expect(state()).not.toHaveProperty('currentRunId')
    expect(activeStreams).toBe(1); expect(maximumStreams).toBe(1)
    await toChat(); await toWorkbench()
    expect(activeStreams).toBe(1); expect(maximumStreams).toBe(1)
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).includes('/events'))).toHaveLength(1)
    wrapper!.unmount(); wrapper = undefined; await settle()
    expect(activeStreams).toBe(0); expect(adapter.stop).toHaveBeenCalled()
  })

  it('protects a hidden dirty Workbench from unrelated navigation and Mission cache eviction', async () => {
    const doc = new TextDocument('file:dirty', 'saved', 'v1')
    vi.spyOn(workspaceDocuments, 'open').mockResolvedValue(doc)
    const { router } = await mountShell('/agentos/missions/mission/workspace?runId=run')
    requestOpenFile({ missionId: 'mission', workspaceRoot: '/workspace', relativePath: 'dirty.txt', name: 'dirty.txt' })
    await settle(); await wrapper!.get('.file-buffer').setValue('keep me')
    const old = state(); const confirm = vi.spyOn(window, 'confirm').mockReturnValue(false)
    await toChat(); expect(confirm).not.toHaveBeenCalled()
    await router.push('/history'); await settle(); expect(router.currentRoute.value.path).toBe('/chat')
    await router.push('/agentos/missions/another/workspace?runId=run'); await settle()
    expect(router.currentRoute.value.path).toBe('/chat'); expect(doc.getText()).toBe('keep me')
    confirm.mockReturnValue(true)
    await router.push('/agentos/missions/another/workspace?runId=run'); await settle()
    expect(state().$.uid).not.toBe(old.$.uid); expect(state().missionId).toBe('another')
    expect(confirm).toHaveBeenCalledTimes(3)
  })

  it('D: a late projection cannot override browser Run selection or remount the Workbench', async () => {
    const { router } = await mountShell('/agentos/missions/mission/workspace?runId=run')
    const uid = state().$.uid
    let deliver!: (value: any) => void
    vi.mocked(agentosApi.getMissionWorkspace).mockImplementationOnce(() => new Promise(ok => { deliver = ok }))
    await router.push('/agentos/missions/mission/workspace?runId=late-run'); await flushPromises()
    await router.push('/agentos/missions/mission/workspace?runId=run'); await settle()
    deliver(projection('mission', 'late-run')); await settle()
    expect(state().$.uid).toBe(uid); expect(state().selectedRunId).toBe('run')
    expect(state().projection.activeRun.runId).toBe('run')
    expect(router.currentRoute.value.query.runId).toBe('run')
  })

  it('D: an already pending Chat launch cannot rewrite the visible Workbench Run when it returns', async () => {
    const { chat, router, clear } = await mountShell()
    let deliver!: (value: any) => void
    vi.spyOn(chat, 'upgradeToWorkflow').mockReturnValue(new Promise(ok => { deliver = ok }))
    const view = wrapper!.findComponent(ChatView).vm as any
    await wrapper!.get('.composer-card textarea').setValue('already requested launch')
    const starting = view.upgradeChatToWorkflow()
    expect(chat.upgradeToWorkflow).toHaveBeenCalledTimes(1)
    await toWorkbench()
    vi.mocked(workflowApi.getWorkflowProgress).mockClear()
    deliver({ binding: { ...binding(), missionId: 'another-mission', runId: 'late-created-run' } })
    await starting; await settle()
    expect(router.currentRoute.value.path).toBe('/agentos/missions/mission/workspace')
    expect(router.currentRoute.value.query.runId).toBe('run')
    expect(state().selectedRunId).toBe('run')
    expect(workflowApi.getWorkflowProgress).not.toHaveBeenCalled()
    expect(clear).not.toHaveBeenCalled()
  })

  it('E: a denied Conversation or mismatched Mission fails closed without navigating to cached history', async () => {
    const { router, clear } = await mountShell('/agentos/missions/mission/workspace?runId=run')
    vi.mocked(conversationApi.getConversation).mockRejectedValue(new Error('403'))
    await toChat()
    expect(router.currentRoute.value.path).toBe('/agentos/missions/mission/workspace')
    vi.mocked(conversationApi.getConversation).mockImplementation(async contextId => ({ contextId, workspaceMode: 'chat' } as any))
    await toChat()
    vi.mocked(agentosApi.getWorkflowRun).mockResolvedValue({ runId: 'run', missionId: 'other', status: 'running' } as any)
    await toWorkbench()
    expect(router.currentRoute.value.path).toBe('/chat'); expect(clear).not.toHaveBeenCalled()
  })

  it('E: a direct Mission link with no Binding falls back to the original Chat without inventing task identity', async () => {
    const { chat, router, clear } = await mountShell('/agentos/missions/mission/workspace?runId=run')
    chat.workflowBindings = {}
    await toChat()
    expect(router.currentRoute.value.path).toBe('/chat')
    expect(router.currentRoute.value.query.contextId).toBe('ctx')
    expect(router.currentRoute.value.query.missionId).toBeUndefined()
    expect(router.currentRoute.value.query.runId).toBeUndefined()
    expect(chat.workflowBindings).toEqual({}); expect(clear).not.toHaveBeenCalled()
  })

  it('F: browser back/forward retains the cached pair; a different Conversation uses its own slot and history', async () => {
    const { router, chat } = await mountShell()
    const original = wrapper!.findComponent(ChatView).vm.$.uid
    await wrapper!.get('.composer-card textarea').setValue('retained')
    await toWorkbench(); const mission = state()
    router.back(); await settle()
    expect(wrapper!.findComponent(ChatView).vm.$.uid).toBe(original)
    router.forward(); await settle(); expect(state().$.uid).toBe(mission.$.uid)
    await router.push('/history'); await settle()
    await router.push('/chat?workspace=chat&contextId=different'); await settle()
    expect(wrapper!.findComponent(ChatView).vm.$.uid).not.toBe(original)
    expect(chat.contextId).toBe('different'); expect(chatApi.getHistory).toHaveBeenCalledWith('different')
    expect(chat.messages[0].content).toBe('restored from history')
    expect((wrapper!.get('.composer-card textarea').element as HTMLTextAreaElement).value).toBe('')
    await router.push('/chat?workspace=chat&newConversation=1'); await settle()
    expect(chat.contextId).toBeNull(); expect(chat.messages).toEqual([])
    expect(localStorage.getItem('chat.workflow_draft_conversation_id')).not.toBe('draft:original')
  })

  it('F: a fresh Shell reconstructs a Conversation from history rather than persisting a KeepAlive instance', async () => {
    const first = await mountShell(); const original = wrapper!.findComponent(ChatView).vm.$.uid
    await wrapper!.get('.composer-card textarea').setValue('memory only')
    wrapper!.unmount(); wrapper = undefined; await settle()
    const second = await mountShell('/chat?workspace=chat&contextId=ctx', null)
    expect(wrapper!.findComponent(ChatView).vm.$.uid).not.toBe(original)
    expect(second.chat).not.toBe(first.chat)
    expect(second.chat.messages[0].content).toBe('restored from history')
    expect(second.chat.currentRoleId).toBe('original-role')
    expect((wrapper!.get('.composer-card textarea').element as HTMLTextAreaElement).value).toBe('')
  })

  it.each([false, true])('R1: a late Agent launch stays with A when B was preloaded=%s', async preloaded => {
    vi.mocked(agentosApi.getWorkflowRun).mockImplementation(async runId => ({
      runId, missionId: 'mission', status: 'completed', steps: [], input: {}, output: {}, trace: [], checkpoints: []
    } as any))
    const launch = deferred<any>()
    const create = vi.spyOn(workflowApi, 'startWorkflowAsync').mockReturnValue(launch.promise)
    const { chat, router } = await mountShell('/chat?workspace=agent&contextId=A', 'A')
    chat.addWorkflowBinding({ ...binding('B'), conversationAliases: [], runId: 'run-B', acgTaskId: 'run-B' })
    const original = wrapper!.findComponent(ChatView).vm.$.uid
    await wrapper!.get('.composer-card textarea').setValue('A submitted objective')
    await wrapper!.get('.composer-send').trigger('click'); await settle()
    expect(create).toHaveBeenCalledTimes(1)
    expect(create.mock.calls[0][0].input).toMatchObject({ conversationId: 'A', source: 'agent' })
    expect(chat.getLatestWorkflowBinding('A')?.runId).toBe('run')
    if (preloaded) await chat.loadHistory('B')
    await router.push('/chat?workspace=agent&contextId=B&runId=run-B'); await settle()
    expect(chat.contextId).toBe('B'); expect(chat.isLoadingConversation).toBe(false)
    expect(chatApi.getHistory).toHaveBeenCalledWith('B')
    expect(chat.messages[0].content).toBe('restored from history')
    const visible = wrapper!.findComponent(ChatView).vm as any
    expect(visible.$.uid === original).toBe(preloaded)
    expect(visible.activeWorkflowRunId).toBe('run-B')
    expect(chat.pendingMissionLaunch('A')?.submissionState).toBe('submitting')
    expect(create.mock.calls[0][1]?.signal?.aborted).not.toBe(true)
    const messages = JSON.stringify(chat.messages)
    await wrapper!.get('.composer-card textarea').setValue('B unsent text')
    launch.resolve({ runId: 'late-A', missionId: 'mission', status: 'running' }); await settle()
    expect(router.currentRoute.value.path).toBe('/chat')
    expect(router.currentRoute.value.query).toMatchObject({ contextId: 'B', runId: 'run-B' })
    expect(visible.activeWorkflowRunId).toBe('run-B')
    expect(visible.selectedConversationId).toBe('B')
    expect(visible.inputText).toBe('B unsent text'); expect(visible.workflowStartError).toBeNull()
    expect(JSON.stringify(chat.messages)).toBe(messages)
    expect(chat.getLatestWorkflowBinding('A')).toMatchObject({ conversationId: 'A', runId: 'late-A' })
    expect(chat.getLatestWorkflowBinding('B')).toMatchObject({ conversationId: 'B', runId: 'run-B' })
    expect(useWorkflowRunsStore().references['late-A'].conversationId).toBe('A')
    expect(chat.pendingMissionLaunch('A')).toBeNull()
    await router.push('/chat?workspace=agent&contextId=A'); await settle()
    expect((wrapper!.findComponent(ChatView).vm as any).activeWorkflowRunId).toBe('late-A')
    await toWorkbench(); await toChat(); await toWorkbench(); await toChat()
    expect(router.currentRoute.value.query).toMatchObject({ contextId: 'A', runId: 'late-A' })
    expect(create).toHaveBeenCalledTimes(1)
  })

  it.each([false, true])('R1: A failure never restores its error or input into B when preloaded=%s', async preloaded => {
    const launch = deferred<any>()
    const create = vi.spyOn(workflowApi, 'startWorkflowAsync').mockReturnValue(launch.promise)
    const { chat, router } = await mountShell('/chat?workspace=agent&contextId=A', 'A')
    await wrapper!.get('.composer-card textarea').setValue('A failed objective')
    await wrapper!.get('.composer-send').trigger('click'); await settle()
    expect(create).toHaveBeenCalledTimes(1)
    if (preloaded) await chat.loadHistory('B')
    await router.push('/chat?workspace=agent&contextId=B'); await settle()
    await wrapper!.get('.composer-card textarea').setValue('B keeps this input')
    const visible = wrapper!.findComponent(ChatView).vm as any
    const messages = JSON.stringify(chat.messages)
    launch.reject(new Error('A failed')); await settle()
    expect(visible.workflowStartError).toBeNull()
    expect(visible.inputText).toBe('B keeps this input')
    expect(visible.loading).toBe(false); expect(visible.isSubmittingWorkflow).toBe(false)
    expect(JSON.stringify(chat.messages)).toBe(messages)
    expect(router.currentRoute.value.query).toEqual({ workspace: 'agent', contextId: 'B' })
    expect(chat.pendingMissionLaunch('A')).not.toBeNull()
    expect(chat.pendingMissionLaunch('B')).toBeNull()
    expect(chat.workflowBindings.B).toBeUndefined()
  })

  it.each(['success', 'failure'])('R1: A %s finally cannot finish B own pending launch', async outcome => {
    const a = deferred<any>(), b = deferred<any>()
    const create = vi.spyOn(workflowApi, 'startWorkflowAsync').mockImplementation(request =>
      request.input?.conversationId === 'A' ? a.promise : b.promise)
    const { chat, router } = await mountShell('/chat?workspace=agent&contextId=A', 'A')
    await wrapper!.get('.composer-card textarea').setValue('A objective')
    await wrapper!.get('.composer-send').trigger('click'); await settle()
    await chat.loadHistory('B')
    await router.push('/chat?workspace=agent&contextId=B'); await settle()
    const visible = wrapper!.findComponent(ChatView).vm as any
    await wrapper!.get('.composer-card textarea').setValue('B objective')
    await wrapper!.get('.composer-send').trigger('click'); await settle()
    try {
      expect(create).toHaveBeenCalledTimes(2)
      expect(visible.loading).toBe(true); expect(visible.isSubmittingWorkflow).toBe(true)
      if (outcome === 'success') a.resolve({ runId: 'late-A', missionId: 'mission', status: 'running' })
      else a.reject(new Error('A failed'))
      await settle()
      expect(visible.loading).toBe(true); expect(visible.isSubmittingWorkflow).toBe(true)
      expect(visible.workflowStartError).toBeNull(); expect(visible.inputText).toBe('')
      expect(router.currentRoute.value.query).toEqual({ workspace: 'agent', contextId: 'B' })
      expect(chat.pendingMissionLaunch('B')?.commandSnapshot.semantics?.objective).toBe('B objective')
    } finally {
      a.resolve({ runId: 'late-A', missionId: 'mission', status: 'running' })
      b.resolve({ runId: 'own-B', missionId: 'mission', status: 'running' }); await settle()
    }
    expect(visible.loading).toBe(false); expect(visible.isSubmittingWorkflow).toBe(false)
    expect(visible.activeWorkflowRunId).toBe('own-B')
    expect(router.currentRoute.value.query).toMatchObject({ contextId: 'B', runId: 'own-B' })
    expect(chat.getLatestWorkflowBinding('B')).toMatchObject({ conversationId: 'B', runId: 'own-B' })
    expect(create).toHaveBeenCalledTimes(2)
  })

  it.each(['success', 'failure'])('R1: resumed A %s belongs to its original owner after same-instance navigation', async outcome => {
    const receipt = deferred<any>()
    const create = vi.spyOn(workflowApi, 'startWorkflowAsync').mockRejectedValue(new Error('response lost'))
    const reconcile = vi.spyOn(workflowApi, 'reconcileMissionLaunch').mockReturnValue(receipt.promise)
    const { chat, router } = await mountShell('/chat?workspace=agent&contextId=A', 'A')
    chat.addWorkflowBinding({ ...binding('B'), conversationAliases: [], runId: 'run-B', acgTaskId: 'run-B' })
    await wrapper!.get('.composer-card textarea').setValue('A uncertain objective')
    await wrapper!.get('.composer-send').trigger('click'); await settle()
    const operationId = chat.pendingMissionLaunch('A')!.operationId
    const original = wrapper!.findComponent(ChatView).vm.$.uid
    await wrapper!.findAll('button').find(button => button.text() === '核对并恢复原提交')!.trigger('click')
    await settle(); expect(reconcile).toHaveBeenCalledTimes(1)
    expect(reconcile.mock.calls[0][0].clientRequestId).toBe(operationId)
    await chat.loadHistory('B')
    await router.push('/chat?workspace=agent&contextId=B&runId=run-B'); await settle()
    const visible = wrapper!.findComponent(ChatView).vm as any
    expect(visible.$.uid).toBe(original)
    await wrapper!.get('.composer-card textarea').setValue('B recovery-independent input')
    const messages = JSON.stringify(chat.messages)
    if (outcome === 'success') receipt.resolve({ status: 'CREATED', missionId: 'mission', runId: 'recovered-A',
      run: { missionId: 'mission', runId: 'recovered-A', status: 'running' } })
    else receipt.reject(new Error('A reconciliation failed'))
    await settle()
    expect(visible.activeWorkflowRunId).toBe('run-B'); expect(visible.workflowStartError).toBeNull()
    expect(visible.inputText).toBe('B recovery-independent input')
    expect(visible.isSubmittingWorkflow).toBe(false)
    expect(JSON.stringify(chat.messages)).toBe(messages)
    expect(router.currentRoute.value.query).toMatchObject({ contextId: 'B', runId: 'run-B' })
    expect(chat.getLatestWorkflowBinding('B')?.runId).toBe('run-B')
    if (outcome === 'success') {
      expect(chat.getLatestWorkflowBinding('A')).toMatchObject({ runId: 'recovered-A', clientRequestId: operationId })
      expect(chat.pendingMissionLaunch('A')).toBeNull()
      await router.push('/chat?workspace=agent&contextId=A'); await settle()
      expect((wrapper!.findComponent(ChatView).vm as any).activeWorkflowRunId).toBe('recovered-A')
      await toWorkbench(); await toChat()
    } else expect(chat.pendingMissionLaunch('A')?.operationId).toBe(operationId)
    expect(create).toHaveBeenCalledTimes(1); expect(reconcile).toHaveBeenCalledTimes(1)
  })

  it('R1: a real launch completes while its aliased Conversation is in Workbench and restores without recreation', async () => {
    vi.useFakeTimers()
    const launch = deferred<any>()
    const create = vi.spyOn(workflowApi, 'startWorkflowAsync').mockReturnValue(launch.promise)
    const { chat, router } = await mountShell('/chat?workspace=agent&contextId=ctx&runId=run')
    const uid = wrapper!.findComponent(ChatView).vm.$.uid
    expect(chat.getLatestWorkflowBinding('draft:original')?.conversationId).toBe('ctx')
    await wrapper!.get('.composer-card textarea').setValue('canonical Conversation objective')
    await wrapper!.get('.composer-send').trigger('click'); await settle()
    await toWorkbench()
    launch.resolve({ runId: 'hidden-created', missionId: 'mission', status: 'running' }); await settle()
    expect(router.currentRoute.value.query.runId).toBe('run')
    expect(state().selectedRunId).toBe('run')
    expect(chat.getLatestWorkflowBinding('ctx')?.runId).toBe('hidden-created')
    expect(chat.getLatestWorkflowBinding('draft:original')?.conversationId).toBe('ctx')
    await toChat()
    expect(wrapper!.findComponent(ChatView).vm.$.uid).toBe(uid)
    // Explicit history selection remains selected; new launch is available through
    // its own canonical Binding rather than stealing the current Workbench Run.
    await router.push('/chat?workspace=agent&contextId=ctx&runId=hidden-created'); await settle()
    expect((wrapper!.findComponent(ChatView).vm as any).activeWorkflowRunId).toBe('hidden-created')
    await toWorkbench(); await toChat()
    expect(create).toHaveBeenCalledTimes(1)
    wrapper!.unmount(); wrapper = undefined; await settle()
    expect(activeStreams).toBe(0)
    const polls = vi.mocked(workflowApi.getWorkflowProgress).mock.calls.length
    await vi.advanceTimersByTimeAsync(20000); await settle()
    expect(workflowApi.getWorkflowProgress).toHaveBeenCalledTimes(polls)
  })
})
