import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentosApi, type MissionWorkspaceProjection, type WorkspaceEntry } from '@/services/api/agentos'
import MissionWorkspaceView from './MissionWorkspaceView.vue'
import { chooseFailedRunRetryMode } from '@/utils/retryModeChoice'

vi.mock('@/utils/retryModeChoice', () => ({
  chooseFailedRunRetryMode: vi.fn().mockResolvedValue('successor_run')
}))

const defaultLayoutStubState = {
  leftAutoHidden: false,
  restoreLeftPane: () => undefined
}
let layoutStubState = { ...defaultLayoutStubState }
const mountedWorkspaces: VueWrapper[] = []

const workspaceLayoutStub = {
  setup: () => ({ noop: () => undefined, state: layoutStubState }),
  template: '<div class="workspace-layout-stub"><aside><slot name="left" /></aside><main><slot name="main" :left-auto-hidden="state.leftAutoHidden" :restore-left-pane="state.restoreLeftPane" :right-auto-hidden="false" :right-enabled="true" :right-pane-visible="true" :right-collapsed-by-user="false" :toggle-right-pane="noop" /></main><aside><slot name="right" /></aside><section><slot name="bottom" :collapsed="false" :set-collapsed="noop" :toggle-collapsed="noop" /></section><footer><slot name="status-bar" :collapsed="false" :set-collapsed="noop" :toggle-collapsed="noop" /></footer></div>'
}

const graphEditorStub = {
  props: ['focusNodeId'],
  emits: ['selectSemanticTask', 'openSemanticTask'],
  template: '<div class="graph-editor-stub" :data-focus-node-id="focusNodeId || undefined"><button class="graph-select" @click="$emit(\'selectSemanticTask\', \'capacity\')">select</button><button class="graph-open" @click="$emit(\'openSemanticTask\', \'capacity\')">open</button></div>'
}

let notifyArtifactReady = true
const artifactEditorStub = {
  props: ['entry', 'available', 'runId'],
  emits: ['locateGraph', 'contentReady'],
  mounted(this: any) { if (notifyArtifactReady) this.$emit('contentReady', this.runId) },
  template: '<div class="artifact-editor-stub"><span>{{ entry.name }}</span><span>{{ available ? "available" : "Not available in this Run" }}</span><button class="artifact-locate" :disabled="!available || entry.identityQuality === \'legacy\'" @click="$emit(\'locateGraph\')">locate</button></div>'
}

const missionEditorStub = { template: '<div class="mission-editor-stub">mission.md</div>' }

const progressEditorStub = {
  props: ['entry', 'runId', 'runStatus', 'cancelPending'],
  emits: ['cancelRun'],
  template: '<div class="progress-editor-stub">运行进度 {{ runId }}<button v-if="runStatus === \'running\' || runStatus === \'pending\'" class="progress-editor-stub__cancel" :disabled="cancelPending" @click="$emit(\'cancelRun\')">停止运行</button></div>'
}

const taskEntry = (): WorkspaceEntry => ({
  entryId: 'task:capacity', kind: 'task', name: 'Capacity', group: 'steps', displayOrder: 0,
  semanticTaskKey: 'capacity', taskId: 'task_capacity', objective: 'Form a capacity plan',
  status: 'completed', attemptCount: 1, latestAttemptId: 'attempt_capacity', artifactCount: 1,
  acgNodeId: 'node_capacity', identityQuality: 'canonical'
})

const folders = (): WorkspaceEntry[] => [
  { entryId: 'folder:overview', kind: 'folder', name: 'Overview', group: 'overview', displayOrder: 0 },
  { entryId: 'folder:steps', kind: 'folder', name: 'Steps', group: 'steps', displayOrder: 0 },
  { entryId: 'folder:output', kind: 'folder', name: 'Output', group: 'output', displayOrder: 0 },
  { entryId: 'folder:runs', kind: 'folder', name: 'Runs', group: 'runs', displayOrder: 0 }
]

const runEntries = (): WorkspaceEntry[] => [
  { entryId: 'run:run_1', kind: 'run', name: 'run_1', group: 'runs', displayOrder: 0, runId: 'run_1', status: 'succeeded' },
  { entryId: 'run:run_2', kind: 'run', name: 'run_2', group: 'runs', displayOrder: 1, runId: 'run_2', status: 'running', isActive: true }
]

const artifact = (key = 'primary', id = 'artifact_1', legacy = false): WorkspaceEntry => ({
  entryId: `task:capacity:${key}`, kind: 'artifact', name: `${key}.md`, group: 'steps', displayOrder: 0, parentEntryId: 'task:capacity',
  semanticTaskKey: legacy ? null : 'capacity', artifactKey: key, artifactId: legacy ? null : id,
  contentRef: `manifest_${id}`, mediaType: 'text/markdown', identityQuality: legacy ? 'legacy' : 'canonical', runId: 'run_2'
})

const projection = (overrides: Partial<MissionWorkspaceProjection> = {}): MissionWorkspaceProjection => ({
  mission: { missionId: 'mission_1', userId: 'user_1', goal: '设备人员规划', description: '目标', metadata: { domain: 'ops' }, createdAt: '2026-08-28T00:00:00Z', updatedAt: '2026-08-28T00:00:00Z', status: 'created' },
  activeRun: { runId: 'run_2', status: 'running', createdAt: '2026-08-28T00:02:00Z', isActive: true },
  runs: [
    { runId: 'run_1', status: 'succeeded', createdAt: '2026-08-28T00:01:00Z', isActive: false },
    { runId: 'run_2', status: 'running', createdAt: '2026-08-28T00:02:00Z', isActive: true }
  ],
  activeGraph: { graphId: 'graph_2', nodes: [{ nodeId: 'node_capacity', nodeType: 'step', name: 'Capacity' }], edges: [] },
  graphNodes: [{ acgNodeId: 'node_capacity', nodeType: 'step', name: 'Capacity', semanticTaskKey: 'capacity', taskId: 'task_capacity', identityQuality: 'canonical', displayOrder: 0 }],
  diagnostics: [],
  entries: [
    ...folders(),
    { entryId: 'overview:graph.acg', kind: 'graph', name: 'graph.acg', group: 'overview', displayOrder: 0 },
    { entryId: 'overview:mission.md', kind: 'virtual_document', name: 'mission.md', group: 'overview', displayOrder: 1, content: '# Mission' },
    taskEntry(),
    artifact(),
    ...runEntries()
  ],
  ...overrides
})

const mountWorkspace = async (
  resolved: MissionWorkspaceProjection | ((runId?: string) => MissionWorkspaceProjection) = projection(),
  url = '/agentos/missions/mission_1/workspace'
) => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/agentos/missions/:missionId/workspace', component: MissionWorkspaceView }]
  })
  await router.push(url)
  await router.isReady()
  const getWorkspace = vi.isMockFunction(agentosApi.getMissionWorkspace)
    ? vi.mocked(agentosApi.getMissionWorkspace)
    : vi.spyOn(agentosApi, 'getMissionWorkspace')
  if (!getWorkspace.getMockImplementation()) {
    getWorkspace.mockImplementation(async (_missionId, options) => {
      return typeof resolved === 'function' ? resolved(options.runId) : resolved
    })
  }
  const getRun = vi.isMockFunction(agentosApi.getWorkflowRun)
    ? vi.mocked(agentosApi.getWorkflowRun)
    : vi.spyOn(agentosApi, 'getWorkflowRun')
  if (!getRun.getMockImplementation()) {
    getRun.mockImplementation(async runId => ({
      runId,
      missionId: 'mission_1',
      workflowId: 'workflow_1',
      domain: 'ops',
      status: (typeof resolved === 'function' ? resolved(runId)?.activeRun?.status : resolved.activeRun?.status) || 'succeeded',
      steps: []
    } as any))
  }
  vi.spyOn(agentosApi, 'getWorkflowTrace').mockResolvedValue({
    runId: 'run_2', missionId: 'mission_1', workflowId: 'workflow_1', domain: 'ops', status: 'succeeded', eventCount: 0, events: []
  } as any)
  vi.spyOn(agentosApi, 'getRunProvenance').mockResolvedValue({ runId: 'run_2', events: [], productions: [], consumptions: [], interactions: [] })
  vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [], total: 0 })
  vi.spyOn(agentosApi, 'getExecutionTree').mockResolvedValue({ nodes: [] } as any)
  vi.spyOn(agentosApi, 'listWorkflowReviews').mockResolvedValue({ items: [] } as any)
  vi.spyOn(agentosApi, 'listRunContextPacks').mockResolvedValue({ items: [] } as any)
  vi.spyOn(agentosApi, 'getCopilot').mockResolvedValue({ runId: 'run_2', status: 'completed', revision: 0,
    modelAvailable: false, question: null, humanAnswers: [], exchanges: [], decision: null, steps: [] })
  const wrapper = mount(MissionWorkspaceView, {
    global: {
      plugins: [router],
      stubs: {
        WorkbenchLayout: workspaceLayoutStub,
        GraphEditor: graphEditorStub,
        ArtifactEditor: artifactEditorStub,
        MissionEditor: missionEditorStub,
        RunProgressEditor: progressEditorStub,
        'el-icon': true
      }
    }
  })
  mountedWorkspaces.push(wrapper)
  await flushPromises()
  return { wrapper, router }
}

describe('MissionWorkspaceView', () => {
  afterEach(async () => {
    for (const wrapper of mountedWorkspaces.splice(0)) if (wrapper.exists()) wrapper.unmount()
    await flushPromises()
    notifyArtifactReady = true
    layoutStubState = { ...defaultLayoutStubState }
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('loads one Mission Workspace projection and renders the project shell', async () => {
    const { wrapper } = await mountWorkspace()
    expect(agentosApi.getMissionWorkspace).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('PROJECT')
    expect(wrapper.text()).toContain('EXPLORER')
    expect(wrapper.find('.editor-inspector-trigger').attributes('aria-label')).toBe('收起 Inspector')
    expect(wrapper.find('.editor-navigator-trigger').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('MISSION WORKSPACE')
  })

  it('switches Inspector and ACG Copilot inside the shared right sidebar', async () => {
    const { wrapper } = await mountWorkspace()
    const copilotTrigger = () => wrapper.findAll('.editor-auxiliary-trigger')
      .find(trigger => trigger.attributes('title').includes('ACG Copilot'))!

    expect(wrapper.find('.secondary-sidebar').exists()).toBe(true)
    expect(wrapper.find('.auxiliary-sidebar').exists()).toBe(false)
    expect(wrapper.findAll('.editor-auxiliary-trigger')).toHaveLength(4)
    expect(wrapper.findAll('.editor-auxiliary-trigger').some(trigger => trigger.attributes('title').includes('文件'))).toBe(true)
    expect(wrapper.findAll('.editor-auxiliary-trigger').some(trigger => trigger.attributes('title').includes('搜索'))).toBe(true)
    expect(wrapper.findAll('.editor-auxiliary-trigger').some(trigger => trigger.attributes('title').includes('源代码管理'))).toBe(true)
    expect(copilotTrigger().attributes('aria-label')).toBe('打开 ACG Copilot')

    await copilotTrigger().trigger('click')

    expect(wrapper.find('.secondary-sidebar').exists()).toBe(false)
    expect(wrapper.get('.auxiliary-sidebar').attributes('aria-label')).toBe('ACG Copilot')
    expect(wrapper.get('.auxiliary-sidebar .acg-copilot').exists()).toBe(true)
    expect(copilotTrigger().attributes('aria-label')).toBe('收起 ACG Copilot')
    expect(wrapper.get('.editor-inspector-trigger').attributes('aria-label')).toBe('打开 Inspector')

    await wrapper.get('.editor-inspector-trigger').trigger('click')
    expect(wrapper.find('.auxiliary-sidebar').exists()).toBe(false)
    expect(wrapper.find('.secondary-sidebar').exists()).toBe(true)
    expect(wrapper.get('.editor-inspector-trigger').attributes('aria-label')).toBe('收起 Inspector')
    expect(wrapper.find('.auxiliary-drawer').exists()).toBe(false)
  })

  it('offers a click trigger to bring back the auto-hidden left navigator', async () => {
    const restoreLeftPane = vi.fn()
    layoutStubState.leftAutoHidden = true
    layoutStubState.restoreLeftPane = restoreLeftPane
    const { wrapper } = await mountWorkspace()

    expect(wrapper.find('.editor-navigator-trigger').attributes('aria-label')).toBe('唤醒项目导航')
    await wrapper.find('.editor-navigator-trigger').trigger('click')
    expect(restoreLeftPane).toHaveBeenCalledTimes(1)
  })

  it('opens the live progress tab for an active Run with graph.acg one click away', async () => {
    const { wrapper } = await mountWorkspace()
    const tabs = wrapper.findAll('.editor-tab')
    expect(tabs[0].text()).toContain('运行进度')
    expect(tabs.map(tab => tab.text()).some(text => text.includes('mission.md'))).toBe(true)
    expect(tabs.map(tab => tab.text()).some(text => text.includes('graph.acg'))).toBe(true)
    expect(wrapper.find('.progress-editor-stub').exists()).toBe(true)
    expect(wrapper.find('.editor-group__toolbar').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('最终答案')
  })

  it('reads the foreground deliverable before starting runtime observations', async () => {
    notifyArtifactReady = false
    const completed = projection({
      activeRun: { runId: 'run_2', status: 'succeeded', createdAt: '2026-08-28T00:02:00Z', isActive: true },
      entries: [{ entryId: 'artifact:final', kind: 'artifact', name: 'final.md', group: 'output', displayOrder: 0,
        artifactKey: 'final', artifactType: 'run_deliverable', artifactId: 'artifact_final', contentRef: 'manifest_final', identityQuality: 'canonical', runId: 'run_2' }]
    })
    const { wrapper } = await mountWorkspace(completed)
    expect(agentosApi.getWorkflowTrace).not.toHaveBeenCalled()
    wrapper.findComponent(artifactEditorStub).vm.$emit('contentReady', 'run_2')
    await flushPromises()
    expect(agentosApi.getWorkflowTrace).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('opens a canonical Run deliverable by default for a completed Run', async () => {
    const completed = projection({
      activeRun: { runId: 'run_1', status: 'succeeded', createdAt: '2026-08-28T00:01:00Z', isActive: true },
      runs: [{ runId: 'run_1', status: 'succeeded', createdAt: '2026-08-28T00:01:00Z', isActive: true }],
      entries: [
        ...folders(),
        { entryId: 'overview:graph.acg', kind: 'graph', name: 'graph.acg', group: 'overview', displayOrder: 0 },
        { entryId: 'overview:mission.md', kind: 'virtual_document', name: 'mission.md', group: 'overview', displayOrder: 1, content: '# Mission' },
        { entryId: 'artifact:final', kind: 'artifact', name: 'final.md', group: 'output', displayOrder: 0, artifactKey: 'final', artifactType: 'run_deliverable', artifactId: 'artifact_final', contentRef: 'manifest_final', identityQuality: 'canonical', runId: 'run_1' }
      ]
    })
    const { wrapper } = await mountWorkspace(completed)
    expect(wrapper.find('.artifact-editor-stub').text()).toContain('final.md')
    expect(wrapper.find('.editor-tab.is-active').text()).toContain('final.md')
  })

  it('refuses to stop a selected Run without authoritative current identity', async () => {
    vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const cancel = vi.spyOn(agentosApi, 'cancelWorkflowRun').mockResolvedValue({
      runId: 'run_2', missionId: 'mission_1', workflowId: 'workflow_1', domain: 'ops', status: 'cancelled', steps: []
    } as any)
    const { wrapper } = await mountWorkspace()

    await wrapper.find('.progress-editor-stub__cancel').trigger('click')
    await flushPromises()

    expect(cancel).not.toHaveBeenCalled()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
    expect(wrapper.find('.progress-editor-stub__cancel').exists()).toBe(true)
  })

  it('opens mission.md and artifacts as separate tabs without duplicate identities', async () => {
    const { wrapper } = await mountWorkspace()
    const entries = wrapper.findAll('.workspace-tree__entry')
    await entries.find(item => item.text().includes('mission.md'))?.trigger('click')
    await entries.find(item => item.text().includes('primary.md'))?.trigger('click')
    await entries.find(item => item.text().includes('primary.md'))?.trigger('click')
    expect(wrapper.findAll('.editor-tab')).toHaveLength(4)
    expect(wrapper.find('.artifact-editor-stub').text()).toContain('primary.md')
  })

  it('closes the active editor and activates the neighboring tab', async () => {
    const { wrapper } = await mountWorkspace()
    const mission = wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('mission.md'))
    await mission?.trigger('click')
    await wrapper.find('.editor-tab.is-active .editor-tab__close').trigger('click')
    expect(wrapper.findAll('.editor-tab')).toHaveLength(2)
    expect(wrapper.findAll('.editor-tab').at(-1)?.text()).toContain('graph.acg')
  })

  const activateGraphTab = async (wrapper: VueWrapper) => {
    const tab = wrapper.findAll('.editor-tab').find(tab => tab.text().includes('graph.acg'))
    await tab?.find('.editor-tab__main').trigger('click')
  }

  it('streams one shared runtime store into the formal Workbench inspector before completion', async () => {
    const encoder = new TextEncoder()
    let pendingRead: ((value: { done: boolean; value?: Uint8Array }) => void) | null = null
    const queued: Uint8Array[] = []
    const reader = {
      read: vi.fn(() => {
        const value = queued.shift()
        if (value) return Promise.resolve({ done: false, value })
        return new Promise<{ done: boolean; value?: Uint8Array }>(resolve => { pendingRead = resolve })
      })
    }
    const push = (type: string, payload: Record<string, unknown>) => {
      const value = encoder.encode(`event: ${type}\ndata: ${JSON.stringify(payload)}\n\n`)
      if (pendingRead) {
        const resolve = pendingRead
        pendingRead = null
        resolve({ done: false, value })
      } else queued.push(value)
    }
    localStorage.setItem('token', 'workspace-runtime-token')
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, body: { getReader: () => reader } })
    vi.stubGlobal('fetch', fetchMock)
    const formalRunId = 'run_formal_streaming'
    const formal = projection({
      activeRun: { runId: formalRunId, status: 'running', createdAt: '2026-08-28T00:02:00Z', isActive: true },
      runs: [{ runId: formalRunId, status: 'running', createdAt: '2026-08-28T00:02:00Z', isActive: true }],
      entries: projection().entries.map(entry => entry.kind === 'run' && entry.runId === 'run_2'
        ? { ...entry, entryId: `run:${formalRunId}`, name: formalRunId, runId: formalRunId }
        : entry)
    })
    const { wrapper } = await mountWorkspace(formal)
    await activateGraphTab(wrapper)
    await wrapper.find('.graph-select').trigger('click')

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
    const [streamUrl, streamOptions] = fetchMock.mock.calls[0]
    expect(streamUrl).toContain(`/api/agentos/v2/runs/${formalRunId}/events`)
    expect(streamOptions.headers.Authorization).toBe('Bearer workspace-runtime-token')
    const event = (sequence: number, eventType: string, payload: Record<string, unknown> = {}) => ({
      eventId: `runtime-${sequence}`,
      eventType,
      runId: formalRunId,
      nodeId: 'node_capacity',
      attemptId: 'attempt-stream-1',
      sequence,
      timestamp: new Date(Date.now() + sequence).toISOString(),
      payload
    })

    push('node.started', event(1, 'node.started'))
    push('model.started', event(2, 'model.started', {
      provider: 'fake-provider', model: 'fake-streaming-model', streamingCapability: true
    }))
    push('model.first_token', event(3, 'model.first_token', { elapsedMs: 12 }))
    push('model.output.delta', event(4, 'model.output.delta', { delta: 'A' }))
    await vi.waitFor(() => expect(wrapper.find('[data-testid="formal-live-output"]').text()).toBe('A'))
    expect(wrapper.text()).toContain('STREAMING')

    push('model.output.delta', event(5, 'model.output.delta', { delta: 'B' }))
    await vi.waitFor(() => expect(wrapper.find('[data-testid="formal-live-output"]').text()).toBe('AB'))
    expect(wrapper.text()).not.toContain('COMPLETED')

    wrapper.unmount()
    await flushPromises()
    expect(streamOptions.signal.aborted).toBe(true)
    localStorage.removeItem('token')
  })

  it('maps a graph double click to the matching TaskEditor', async () => {
    const { wrapper } = await mountWorkspace()
    await activateGraphTab(wrapper)
    await wrapper.find('.graph-open').trigger('click')
    expect(wrapper.find('.task-editor').exists()).toBe(true)
    expect(wrapper.find('.editor-group__surface--task').exists()).toBe(true)
    expect(wrapper.find('.task-editor').text()).toContain('Capacity')
  })

  it('routes Task metadata into document-oriented Inspector tabs', async () => {
    const { wrapper } = await mountWorkspace()
    await wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('Capacity'))?.trigger('click')
    await flushPromises()

    expect(wrapper.find('.task-editor__heading').exists()).toBe(true)
    expect(wrapper.findAll('.runtime-inspector__tabs button').map(button => button.text())).toEqual([
      '任务信息', '证据与引用', '相关文件', '讨论'
    ])
    expect(wrapper.find('.runtime-inspector__tab-panel').text()).toContain('Execution')

    await wrapper.findAll('.runtime-inspector__tabs button')[2].trigger('click')
    expect(wrapper.find('.related-files').text()).toContain('primary.md')

    await wrapper.findAll('.runtime-inspector__tabs button')[1].trigger('click')
    expect(wrapper.find('.runtime-inspector__evidence-list').exists()).toBe(true)
  })

  it('keeps multiple Artifacts inside the matching TaskEditor', async () => {
    const multi = projection({ entries: [...projection().entries, artifact('assumptions', 'artifact_2')] })
    const { wrapper } = await mountWorkspace(multi)
    await activateGraphTab(wrapper)
    await wrapper.find('.graph-open').trigger('click')
    expect(wrapper.find('.artifact-choice').exists()).toBe(false)
    expect(wrapper.findAll('.task-editor__artifacts button')).toHaveLength(2)
    await wrapper.findAll('.task-editor__artifacts button')[0].trigger('click')
    await flushPromises()
    expect(wrapper.find('.artifact-editor-stub').text()).toContain('assumptions.md')
  })

  it('selects a graph node even when no artifact is available', async () => {
    const noArtifact = projection({ entries: projection().entries.filter(item => item.kind !== 'artifact') })
    const { wrapper } = await mountWorkspace(noArtifact)
    await activateGraphTab(wrapper)
    await wrapper.find('.graph-open').trigger('click')
    expect(wrapper.find('.artifact-choice').exists()).toBe(false)
    expect(wrapper.find('.task-editor').exists()).toBe(true)
  })

  it('locates a canonical artifact in graph and keeps the artifact tab open', async () => {
    const { wrapper } = await mountWorkspace()
    const artifactRow = wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('primary.md'))
    await artifactRow?.trigger('click')
    await wrapper.find('.artifact-locate').trigger('click')
    expect(wrapper.find('.graph-editor-stub').exists()).toBe(true)
    expect(wrapper.findAll('.editor-tab')).toHaveLength(4)
  })

  it('locates a task in graph and passes its node id after graph mount', async () => {
    const { wrapper } = await mountWorkspace()
    await wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('Capacity'))?.trigger('click')
    await wrapper.find('.task-editor__actions button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.graph-editor-stub').attributes('data-focus-node-id')).toBe('node_capacity')
  })

  it('disables graph positioning for legacy artifacts', async () => {
    const legacy = projection({ entries: [...folders(), ...runEntries(), artifact('legacy', 'legacy', true), { entryId: 'overview:graph.acg', kind: 'graph', name: 'graph.acg', group: 'overview', displayOrder: 0 }, { entryId: 'overview:mission.md', kind: 'virtual_document', name: 'mission.md', group: 'overview', displayOrder: 1, content: '# Mission' }] })
    const { wrapper } = await mountWorkspace(legacy)
    await wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('legacy.md'))?.trigger('click')
    expect(wrapper.find('.artifact-locate').attributes('disabled')).toBeDefined()
  })

  it('switches from current to historical Run through a new workspace request', async () => {
    vi.spyOn(agentosApi, 'getWorkflowRun').mockImplementation(async runId => ({ runId, missionId: 'mission_1', status: runId === 'run_1' ? 'succeeded' : 'running', steps: [], lineage: runId === 'run_1' ? { supersededByRunId: 'run_2' } : {} } as any))
    const historical = projection({ activeRun: { runId: 'run_1', status: 'succeeded', createdAt: '2026-08-28T00:01:00Z', isActive: true }, entries: projection().entries.filter(item => item.entryId !== 'task:capacity:primary') })
    const getWorkspace = vi.spyOn(agentosApi, 'getMissionWorkspace').mockImplementation(async (_id, options) => options.runId === 'run_1' ? historical : projection())
    const { wrapper } = await mountWorkspace()
    await wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('mission.md'))?.trigger('click')
    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    await wrapper.findAll('.workbench-status-bar__run-item').find(item => item.text().includes('run_1'))?.trigger('click')
    await flushPromises()
    expect(getWorkspace).toHaveBeenLastCalledWith('mission_1', expect.objectContaining({ runId: 'run_1' }))
    expect(wrapper.find('.editor-tab.is-active').text()).toContain('运行进度')
    expect(wrapper.find('.progress-editor-stub').text()).toContain('run_1')
    expect(wrapper.text()).toContain('Historical / Read-only')
  })

  it('switches historical back to the current Run explicitly', async () => {
    const historical = projection({ activeRun: { runId: 'run_1', status: 'succeeded', createdAt: '2026-08-28T00:01:00Z', isActive: true }, entries: projection().entries.filter(item => item.entryId !== 'task:capacity:primary') })
    const { wrapper } = await mountWorkspace(runId => runId === 'run_1' ? historical : projection())
    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    await wrapper.findAll('.workbench-status-bar__run-item').find(item => item.text().includes('run_1'))?.trigger('click')
    await flushPromises()
    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    await wrapper.findAll('.workbench-status-bar__run-item').find(item => item.text().includes('run_2'))?.trigger('click')
    await flushPromises()
    expect(agentosApi.getMissionWorkspace).toHaveBeenLastCalledWith('mission_1', expect.objectContaining({ runId: 'run_2' }))
    expect(wrapper.text()).not.toContain('Historical / Read-only')
  })

  it('creates a successor from the selected terminal Run and switches to it', async () => {
    const source = projection({
      activeRun: { runId: 'run_1', status: 'succeeded', createdAt: '2026-08-28T00:01:00Z', isActive: true }
    })
    const successor = projection({
      activeRun: { runId: 'run_3', status: 'running', createdAt: '2026-08-28T00:03:00Z', isActive: true },
      runs: [...source.runs, { runId: 'run_3', status: 'running', createdAt: '2026-08-28T00:03:00Z', isActive: true }]
    })
    vi.spyOn(agentosApi, 'getWorkflowHistoryConfig').mockResolvedValue({
      runId: 'run_1', reviewMode: 'auto', enabledPluginIds: ['plugin_1'], input: { taskGoal: '设备规划' }
    })
    const rerun = vi.spyOn(agentosApi, 'rerunWorkflowAsync').mockResolvedValue({
      runId: 'run_3', missionId: 'mission_1', workflowId: 'workflow_1', domain: 'ops', status: 'pending', steps: [], lineage: { sourceRunId: 'run_1' }
    } as any)
    const { wrapper, router } = await mountWorkspace(runId => runId === 'run_3' ? successor : source, '/agentos/missions/mission_1/workspace?runId=run_1')

    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    await wrapper.find('.workbench-status-bar__run-action').trigger('click')
    await flushPromises()

    expect(rerun).toHaveBeenCalledWith('mission_1', expect.objectContaining({
      sourceRunId: 'run_1', rerunReason: 'manual_rerun', input: { taskGoal: '设备规划' }, clientRequestId: expect.any(String)
    }))
    expect(router.currentRoute.value.query.runId).toBe('run_3')
    expect(agentosApi.getMissionWorkspace).toHaveBeenLastCalledWith('mission_1', expect.objectContaining({ runId: 'run_3' }))
    expect(wrapper.text()).not.toContain('Historical / Read-only')
  })

  it('continues a failed Run from its failed step instead of replaying completed work', async () => {
    vi.mocked(chooseFailedRunRetryMode).mockResolvedValue('successor_run')
    const source = projection({
      activeRun: { runId: 'run_1', status: 'failed', createdAt: '2026-08-28T00:01:00Z', isActive: true }
    })
    const successor = projection({
      activeRun: { runId: 'run_3', status: 'running', createdAt: '2026-08-28T00:03:00Z', isActive: true },
      runs: [...source.runs, { runId: 'run_3', status: 'running', createdAt: '2026-08-28T00:03:00Z', isActive: true }]
    })
    vi.spyOn(agentosApi, 'getWorkflowRun').mockResolvedValue({
      runId: 'run_1', missionId: 'mission_1', workflowId: 'workflow_1', domain: 'ops',
      status: 'failed', runtimeRevision: 9,
      steps: [
        { stepId: 'source', name: 'source', agentName: 'native', status: 'completed' },
        { stepId: 'design', name: 'design', agentName: 'native', status: 'failed' },
        { stepId: 'final', name: 'final', agentName: 'native', status: 'pending' }
      ]
    } as any)
    const resume = vi.spyOn(agentosApi, 'retryWorkflowStepAsync').mockResolvedValue({
      runId: 'run_3', missionId: 'mission_1', workflowId: 'workflow_1', domain: 'ops', status: 'pending', steps: [], lineage: { sourceRunId: 'run_1' }
    } as any)
    const rerun = vi.spyOn(agentosApi, 'rerunWorkflowAsync')
    const { wrapper, router } = await mountWorkspace(
      runId => runId === 'run_3' ? successor : source,
      '/agentos/missions/mission_1/workspace?runId=run_1'
    )

    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    expect(wrapper.find('.workbench-status-bar__run-action').text()).toContain('从失败处继续')
    await wrapper.find('.workbench-status-bar__run-action').trigger('click')
    await flushPromises()

    expect(rerun).not.toHaveBeenCalled()
    expect(resume).toHaveBeenCalledWith('run_1', 'design', expect.objectContaining({
      reason: 'resume_failed', expectedRuntimeRevision: 9, mode: 'successor_run', clientRequestId: expect.any(String)
    }))
    expect(router.currentRoute.value.query.runId).toBe('run_3')
    expect(agentosApi.getMissionWorkspace).toHaveBeenLastCalledWith(
      'mission_1', expect.objectContaining({ runId: 'run_3' })
    )
  })

  it('keeps mission and Run navigation available before identity projection exists', async () => {
    const runtimeOnly = projection({
      activeRun: { runId: 'run_3', status: 'pending', createdAt: '2026-08-28T00:03:00Z', isActive: true },
      runs: [{ runId: 'run_3', status: 'pending', createdAt: '2026-08-28T00:03:00Z', isActive: true }],
      entries: [],
      graphNodes: [],
      activeGraph: null,
      diagnostics: [{ code: 'PLANNING_PROJECTION_PENDING', message: 'pending', severity: 'warning' }]
    })
    const { wrapper } = await mountWorkspace(runtimeOnly, '/agentos/missions/mission_1/workspace?runId=run_3')

    expect(wrapper.text()).toContain('mission.md')
    expect(wrapper.text()).toContain('run_3')
    expect(wrapper.text()).not.toContain('Mission 尚无历史 Run')
  })

  it('refreshes identity task status and artifacts while an active Run executes', async () => {
    vi.useFakeTimers()
    try {
      const first = projection({
        entries: projection().entries.map(item => item.entryId === 'task:capacity'
          ? { ...item, status: 'running', artifactCount: 0 }
          : item)
      })
      const second = projection({
        entries: projection().entries.map(item => item.entryId === 'task:capacity'
          ? { ...item, status: 'completed', artifactCount: 1 }
          : item)
      })
      const getWorkspace = vi.spyOn(agentosApi, 'getMissionWorkspace')
        .mockResolvedValueOnce(first)
        .mockResolvedValue(second)
      const { wrapper } = await mountWorkspace()
      await wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('Capacity'))?.trigger('click')
      expect(wrapper.find('.task-editor__status').text()).toBe('Running')

      await vi.advanceTimersByTimeAsync(8000)
      await flushPromises()

      expect(getWorkspace).toHaveBeenCalledTimes(2)
      expect(wrapper.find('.task-editor__status').text()).toBe('Completed')
      expect(wrapper.find('.task-editor__section--artifacts .task-editor__section-meta').text()).toBe('1')
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps runtime observation visible while a projection refresh is pending', async () => {
    vi.useFakeTimers()
    try {
      let resolveRefresh: (value: MissionWorkspaceProjection) => void = () => undefined
      const refresh = new Promise<MissionWorkspaceProjection>(resolve => {
        resolveRefresh = resolve
      })
      const getWorkspace = vi.spyOn(agentosApi, 'getMissionWorkspace')
        .mockResolvedValueOnce(projection())
        .mockReturnValueOnce(refresh)
      vi.spyOn(agentosApi, 'getWorkflowRun').mockResolvedValue({
        runId: 'run_2', missionId: 'mission_1', workflowId: 'workflow_1', domain: 'ops', status: 'succeeded', steps: []
      } as any)
      const { wrapper } = await mountWorkspace()
      await vi.waitFor(() => expect((wrapper.vm as any).runtimeObservation).not.toBeNull())

      await vi.advanceTimersByTimeAsync(8000)
      await flushPromises()

      expect(getWorkspace).toHaveBeenCalledTimes(2)
      expect((wrapper.vm as any).runtimeObservation).not.toBeNull()

      resolveRefresh(projection())
      await flushPromises()
      wrapper.unmount()
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps the stable artifact tab identity and shows missing content in a historical Run', async () => {
    const historical = projection({ activeRun: { runId: 'run_1', status: 'succeeded', createdAt: '2026-08-28T00:01:00Z', isActive: true }, entries: projection().entries.filter(item => item.entryId !== 'task:capacity:primary') })
    const { wrapper } = await mountWorkspace((_runId) => _runId === 'run_1' ? historical : projection())
    await wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('primary.md'))?.trigger('click')
    await wrapper.find('.workbench-status-bar__run-trigger').trigger('click')
    await wrapper.findAll('.workbench-status-bar__run-item').find(item => item.text().includes('run_1'))?.trigger('click')
    await flushPromises()
    expect(wrapper.find('.editor-tab.is-active').text()).toContain('运行进度')
    await wrapper.findAll('.editor-tab').find(item => item.text().includes('primary.md'))?.find('.editor-tab__main').trigger('click')
    expect(wrapper.find('.artifact-editor-stub').text()).toContain('Not available in this Run')
    expect(wrapper.findAll('.editor-tab')).toHaveLength(4)
  })

  it('shows NO_ACTIVE_RUN diagnostics and falls back to mission.md', async () => {
    const empty = projection({ activeRun: null, entries: [...folders(), { entryId: 'overview:mission.md', kind: 'virtual_document', name: 'mission.md', group: 'overview', displayOrder: 1, content: '# Empty' }, ...runEntries()], diagnostics: [{ code: 'NO_ACTIVE_RUN', message: '没有 Run', severity: 'info' }] })
    const { wrapper } = await mountWorkspace(empty)
    expect(wrapper.find('.workbench-status-bar__tab').text()).toContain('Problems')
    expect(wrapper.find('.workbench-status-bar__tab-count.is-alert').text()).toBe('1')
    expect(wrapper.find('.problems-panel').text()).toContain('NO_ACTIVE_RUN')
    expect(wrapper.text()).toContain('mission.md')
  })

  it('exposes the fixed runtime observation panels through the Workbench registry', async () => {
    const { wrapper } = await mountWorkspace()
    expect(wrapper.findAll('.workbench-status-bar__tab').map(tab => tab.text())).toEqual([
      'Problems0', 'Communication0', 'Trace0', 'Events0', 'Tool Calls0'
    ])
  })

  it('surfaces API failure with a visible retry state', async () => {
    vi.spyOn(agentosApi, 'getMissionWorkspace').mockRejectedValue(new Error('offline'))
    const { wrapper } = await mountWorkspace()
    expect(wrapper.text()).toContain('Mission Workspace unavailable')
    expect(wrapper.text()).toContain('重新加载')
  })

  it('shows a contract error immediately instead of retrying a deterministic 502', async () => {
    const getWorkspace = vi.spyOn(agentosApi, 'getMissionWorkspace').mockRejectedValue({
      response: { status: 502, data: { code: 'AGENTOS_CONTRACT_INVALID' } }
    })
    const { wrapper } = await mountWorkspace()
    expect(getWorkspace).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('Mission Workspace unavailable')
    expect(wrapper.text()).not.toContain('Loading Mission Workspace')
  })

  it('waits for a deferred Run identity projection after the Runtime Run is accepted', async () => {
    vi.useFakeTimers()
    try {
      const getWorkspace = vi.spyOn(agentosApi, 'getMissionWorkspace')
        .mockRejectedValueOnce({ response: { status: 404 } })
        .mockResolvedValue(projection())
      const getRun = vi.spyOn(agentosApi, 'getWorkflowRun').mockResolvedValue({
        runId: 'run_2', missionId: 'mission_1', workflowId: 'workflow_1', domain: 'ops',
        status: 'running', steps: []
      } as any)

      const { wrapper } = await mountWorkspace(projection(), '/agentos/missions/mission_1/workspace?runId=run_2')
      await flushPromises()

      expect(getRun).toHaveBeenCalledWith('run_2', expect.objectContaining({ signal: expect.any(AbortSignal) }))
      expect(getWorkspace).toHaveBeenCalledTimes(1)
      await vi.advanceTimersByTimeAsync(250)
      await flushPromises()

      expect(getWorkspace).toHaveBeenCalledTimes(2)
      expect(wrapper.text()).toContain('PROJECT')
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not request Artifact content while the default graph editor is open', async () => {
    const getContent = vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ manifestId: 'manifest_1', mediaType: 'text/markdown', content: 'body' })
    const { wrapper } = await mountWorkspace()
    expect(getContent).not.toHaveBeenCalled()
    await wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('primary.md'))?.trigger('click')
    await flushPromises()
    expect(getContent).not.toHaveBeenCalled()
  })
})
