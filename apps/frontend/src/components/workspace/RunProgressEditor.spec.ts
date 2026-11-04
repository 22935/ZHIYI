import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RunProgressEditor from './RunProgressEditor.vue'
import type { MissionWorkspaceProjection, WorkspaceEntry, WorkspaceGraphNode } from '@/services/api/agentos'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import { RunRuntimeStore } from '@/workbench/runtime/runtimeEvents'

const traceEvent = (eventId: string, payload: Record<string, any>, overrides: Partial<{ stepId: string | null; eventType: string; timestamp: string; durationMs: number | null }> = {}) => ({
  eventId,
  runId: 'run_1',
  stepId: overrides.stepId ?? null,
  eventType: overrides.eventType ?? 'task_status_changed',
  observation: null,
  timestamp: overrides.timestamp ?? '2026-09-02T00:00:00Z',
  durationMs: overrides.durationMs ?? null,
  status: String(payload.status || ''),
  payload,
  source: 'trace' as const
})

const observation = (events: ReturnType<typeof traceEvent>[], runStatus: string | null = 'running') => ({
  runId: 'run_1',
  runStatus,
  traces: events,
  events: [],
  communication: [],
  toolCalls: [],
  problems: [],
  audit: {},
  provenance: {},
  operational: null,
  recoveryTrace: [],
  contractViolations: [],
  scheduleTrace: [],
  patchRefs: [],
  lowEntropy: {},
  resourceObservation: null,
  unavailableSources: []
}) as unknown as RuntimeObservation

const plannerEvents = () => [
  traceEvent('e1', { planningProgress: true, category: 'planner', kind: 'started' }),
  traceEvent('e2', {
    planningProgress: true, category: 'planner', kind: 'stage_started',
    stage: 'intent_profile', status: 'started', attempt: 1
  }),
  traceEvent('e3', {
    planningProgress: true, category: 'planner', kind: 'plan_parsed',
    stage: 'planning', status: 'plan_parsed', taskCount: 6, dependencyCount: 8
  }),
  traceEvent('e4', {
    planningProgress: true, category: 'planner', kind: 'graph_compiled',
    nodeCount: 5, edgeCount: 11
  }),
  traceEvent('e5', { planningProgress: true, category: 'planner', kind: 'completed' })
]

const graphNodes = (): WorkspaceGraphNode[] => [
  { acgNodeId: 'node_a', nodeType: 'task', name: '需求分析', semanticTaskKey: 'requirements.analysis', displayOrder: 1 },
  { acgNodeId: 'node_b', nodeType: 'task', name: '架构设计', semanticTaskKey: 'architecture.design', displayOrder: 2 }
] as unknown as WorkspaceGraphNode[]

const entry = (overrides: Partial<WorkspaceEntry> = {}): WorkspaceEntry => ({
  entryId: 'overview:progress',
  kind: 'progress',
  name: '运行进度',
  title: '运行进度',
  group: 'overview',
  displayOrder: -1,
  ...overrides
})

const projection = (overrides: Partial<MissionWorkspaceProjection> = {}): MissionWorkspaceProjection => ({
  mission: { missionId: 'mission_1', goal: '为 IC-200 工业控制器设计完整技术方案', description: '', userId: 'u', metadata: {}, createdAt: '', updatedAt: '', status: 'active' },
  runs: [{ runId: 'run_1', status: 'running', createdAt: '2026-09-02T00:00:00Z', completedAt: null, isActive: true }],
  entries: [
    { entryId: 'graph:main', kind: 'graph', name: 'graph.acg', group: 'overview', displayOrder: 1 },
    {
      entryId: 'artifact:req', kind: 'artifact', name: 'requirements.md', group: 'output', displayOrder: 1,
      semanticTaskKey: 'requirements.analysis', artifactId: 'art_1'
    },
    { entryId: 'overview:graph.acg', kind: 'graph', name: 'graph.acg', group: 'overview', displayOrder: 0 }
  ],
  graphNodes: graphNodes(),
  diagnostics: [],
  ...overrides
} as MissionWorkspaceProjection)

const topologyStub = {
  props: ['blueprint', 'focusNodeId', 'runtimePhases', 'stepStates', 'completedStepIds', 'runId'],
  template: '<div data-testid="acg-preview" />'
}

const mountEditor = (props: Record<string, unknown> = {}) => mount(RunProgressEditor, {
  props: {
    entry: entry(),
    projection: projection(),
    graphNodes: graphNodes(),
    runId: 'run_1',
    runtimeObservation: observation(plannerEvents()),
    ...props
  },
  global: { stubs: { AcgTopologyGraph: topologyStub } }
})
const runtimeEvent = (sequence: number, eventType: string) => ({
  eventId: `runtime-${sequence}`,
  eventType,
  runId: 'run_1',
  nodeId: null,
  attemptId: null,
  sequence,
  timestamp: new Date(sequence * 1000).toISOString(),
  payload: {}
})

describe('RunProgressEditor', () => {
  it('shows formal pause/permit/dispatch facts instead of RUNNING before node execution', async () => {
    const value = observation([], 'planning')
    value.run = { runId: 'run_1', missionId: 'mission_1', workflowId: 'workflow', domain: 'test', status: 'planning', steps: [],
      formalControl: { status: 'ACTIVATED_PAUSED', executionAuthorized: false, permitIssued: false, dispatchEligible: false,
        dispatchEnabled: true, commitId: 'c', commitmentRevision: 1, materializationId: 'm', activationId: 'a', graphId: 'g',
        graphVersion: 1, handoffId: null, handoffStatus: null, permitId: null, permitStatus: null, dispatch: null } }
    const wrapper = mountEditor({ runtimeObservation: value })
    expect(wrapper.get('.run-progress__status').text()).toBe('ACTIVATED_PAUSED')
    const control = value.run.formalControl!
    await wrapper.setProps({ runtimeObservation: { ...value, run: { ...value.run, formalControl: { ...control, permitStatus: 'ISSUED' } } } })
    expect(wrapper.get('.run-progress__status').text()).toBe('Permit ISSUED')
    await wrapper.setProps({ runtimeObservation: { ...value, run: { ...value.run, formalControl: { ...control,
      dispatch: { dispatchId: 'd', runId: 'run_1', permitId: 'p', graphVersion: 1, status: 'ACCEPTED' } } } } })
    expect(wrapper.get('.run-progress__status').text()).toBe('Dispatch ACCEPTED')
    wrapper.unmount()
  })
  it('uses selected Run history instead of the current Mission goal', () => {
    const value = projection({ missionDisplay: { objective: 'current goal', sourceType: 'SEMANTIC' },
      selectedRunBasisStatus: 'BOUND', selectedRunBasis: {
        missionId: 'mission_1', basisSchemaVersion: 1, fingerprintVersion: 1, sourceType: 'SEMANTIC',
        sourceRevision: 1, objective: 'historical goal', constraints: [], sourceReferences: [],
        sourceStatus: 'NOT_APPLICABLE', fingerprint: 'abc' } })
    const wrapper = mountEditor({ projection: value })
    expect(wrapper.text()).toContain('historical goal')
    expect(wrapper.text()).not.toContain('current goal')
  })
  it('renders a clickable directory path for the current run document', async () => {
    const wrapper = mountEditor()

    expect(wrapper.get('[aria-label="运行目录层级"]').text()).toContain('OUTLINE')
    expect(wrapper.get('[aria-label="运行目录层级"]').text()).not.toContain('Run 01')
    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')

    const directory = wrapper.get('[aria-label="运行目录层级"]')
    expect(directory.text()).toContain('Planning')
    expect(directory.text()).not.toContain('Intent Profile')
  })

  it('renders the planner as one aggregated group with deterministic result metrics', () => {
    const wrapper = mountEditor()

    const planners = wrapper.findAll('[data-symbol-type="planner"]')
    expect(planners).toHaveLength(1)
    expect(planners[0].text()).toContain('Planning')
    // 内部阶段不得一级平铺为用户可读的"正在理解…"文案
    expect(wrapper.text()).not.toContain('正在理解')
    // 完成后组收起，digest 汇总真实计数
    expect(wrapper.text()).toContain('Task Plan · 6 Tasks · 8 Dependencies')
    expect(wrapper.text()).toContain('ACG')
    expect(wrapper.text()).toContain('5 nodes')
    expect(wrapper.text()).toContain('11 edges')
  })

  it('opens each symbol level in a right-hand column instead of nesting a tree below the row', async () => {
    const wrapper = mountEditor()

    expect(wrapper.findAll('.run-progress__column')).toHaveLength(1)
    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')

    expect(wrapper.findAll('.run-progress__column')).toHaveLength(2)
    expect(wrapper.findAll('.run-progress__column')[1].text()).toContain('Intent Profile')
    expect(wrapper.find('.run-symbol__body').exists()).toBe(false)

    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')
    expect(wrapper.findAll('.run-progress__column')).toHaveLength(2)

    const taskPlan = wrapper.findAll('[data-symbol-type="stage"]').find(item => item.text().includes('Task Plan'))!
    await taskPlan.find('.run-symbol__main').trigger('click')
    expect(wrapper.findAll('.run-progress__column')).toHaveLength(3)
  })

  it('returns to the selected parent column from the breadcrumb', async () => {
    const wrapper = mountEditor()

    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')
    const taskPlan = wrapper.findAll('[data-symbol-type="stage"]').find(item => item.text().includes('Task Plan'))!
    await taskPlan.find('.run-symbol__main').trigger('click')
    expect(wrapper.findAll('.run-progress__column')).toHaveLength(3)

    await wrapper.get('[aria-label="运行目录层级"] button[title="Planning"]').trigger('click')
    expect(wrapper.findAll('.run-progress__column')).toHaveLength(2)
    expect(wrapper.findAll('.run-progress__column')[1].find('.run-progress__column-head').text()).toBe('Planning')
  })

  it('keeps Planning open when the parent synchronizes the selected symbol after the click', async () => {
    const wrapper = mountEditor()

    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')
    await wrapper.setProps({ selectedSymbolId: 'planner:run_1' })

    expect(wrapper.findAll('.run-progress__column')).toHaveLength(2)
    expect(wrapper.findAll('.run-progress__column')[1].text()).toContain('Intent Profile')
  })

  it('reopens Planning automatically when its children arrive after selection', async () => {
    const wrapper = mountEditor({
      graphNodes: [],
      runtimeObservation: observation([])
    })

    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')
    await wrapper.setProps({ selectedSymbolId: 'planner:run_1' })
    expect(wrapper.findAll('.run-progress__column')[1].find('.run-progress__column-head').text()).toBe('INSPECTOR')

    await wrapper.setProps({ runtimeObservation: observation(plannerEvents()) })

    expect(wrapper.findAll('.run-progress__column')).toHaveLength(2)
    expect(wrapper.findAll('.run-progress__column')[1].text()).toContain('Intent Profile')
  })

  it('trims a sibling stage branch before showing a nested leaf inspector', async () => {
    const runtimeStore = new RunRuntimeStore('run_1')
    runtimeStore.apply(runtimeEvent(1, 'planner.started'))
    runtimeStore.apply({
      ...runtimeEvent(2, 'planner.stage.started'),
      payload: { stage: 'relations', callKey: 'relations' }
    })

    const wrapper = mountEditor({ runtimeObservation: observation([]), runtimeStore })
    const detail = wrapper.findAll('[data-symbol-type="stage"]').find(item => item.text().includes('Detail'))!

    await detail.find('.run-symbol__main').trigger('click')

    expect(wrapper.findAll('.run-progress__column')).toHaveLength(3)
    expect(wrapper.findAll('.run-progress__column')[2].find('.run-progress__column-head').text()).toBe('INSPECTOR')
  })

  it('resets an open Execution branch when selecting root-level Planning', async () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        traceEvent('task-1', { status: 'started' }, { stepId: 'node_a', eventType: 'step_started' })
      ])
    })

    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')

    expect(wrapper.findAll('.run-progress__column')).toHaveLength(2)
    expect(wrapper.findAll('.run-progress__column')[1].find('.run-progress__column-head').text()).toBe('INSPECTOR')
    expect(wrapper.findAll('.run-progress__column')[1].text()).toContain('Planning')
  })

  it('lets the graph column use the remaining editor width', async () => {
    const wrapper = mountEditor()

    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')
    await wrapper.get('[data-symbol-type="acg"] .run-symbol__main').trigger('click')

    expect(wrapper.find('.run-progress__column.is-graph-column').exists()).toBe(true)
    expect(wrapper.find('.run-progress__column.is-detail-column').exists()).toBe(false)
    expect(wrapper.find('.run-progress__body').classes()).toContain('is-graph-mode')
  })

  it('shows a flat inspector column for the selected leaf symbol', async () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        ...plannerEvents(),
        traceEvent('t1', { status: 'started' }, { stepId: 'node_a', eventType: 'step_started' }),
        traceEvent('tool-1', { tool: 'web_search', name: 'Read File', status: 'succeeded', latencyMs: 821 }, { stepId: 'node_a', eventType: 'tool_called' })
      ])
    })

    await wrapper.get('[data-symbol-type="tool"] .run-symbol__main').trigger('click')
    expect(wrapper.find('.run-progress__column:last-child .run-progress__column-head').text()).toBe('INSPECTOR')
    expect(wrapper.find('.run-progress__detail').text()).toContain('Read File')
    expect(wrapper.find('.run-progress__detail').text()).toContain('Duration821 ms')
    expect(wrapper.find('.run-progress__detail').text()).toContain('Task')
  })

  it('keeps the parent task activity visible while inspecting a tool', async () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        ...plannerEvents(),
        traceEvent('task-1', { status: 'started' }, { stepId: 'node_a', eventType: 'step_started' }),
        traceEvent('task-2', { status: 'started' }, { stepId: 'node_b', eventType: 'step_started' }),
        traceEvent('tool-2', { tool: 'web_search', name: 'Web Search', status: 'succeeded', latencyMs: 240 }, { stepId: 'node_b', eventType: 'tool_called' })
      ])
    })

    const taskRows = wrapper.findAll('[data-symbol-type="task"]')
    await taskRows[1].find('.run-symbol__main').trigger('click')
    expect(wrapper.findAll('.run-progress__column')[2].text()).toContain('Web Search')

    await wrapper.get('[data-symbol-type="tool"] .run-symbol__main').trigger('click')
    expect(wrapper.findAll('.run-progress__column')[2].text()).toContain('Web Search')
    expect(wrapper.find('.run-progress__column:last-child .run-progress__column-head').text()).toBe('INSPECTOR')
    expect(wrapper.find('.run-progress__detail').text()).toContain('Web Search')
  })

  it('opens the model tool-call chain as the next browser column', async () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        ...plannerEvents(),
        traceEvent('task-2', { status: 'started' }, { stepId: 'node_b', eventType: 'step_started' }),
        traceEvent('model-2', { model: 'glm-5.3-flash' }, { stepId: 'node_b', eventType: 'model_called' }),
        traceEvent('tool-2', { tool: 'web_search', name: 'Web Search', status: 'succeeded' }, { stepId: 'node_b', eventType: 'tool_called' })
      ])
    })

    await wrapper.get('[data-symbol-id="task:architecture.design"] .run-symbol__main').trigger('click')
    await wrapper.get('[data-symbol-type="model"] .run-symbol__main').trigger('click')

    expect(wrapper.findAll('.run-progress__column')[3].text()).toContain('Web Search')
    expect(wrapper.findAll('.run-progress__column')[3].find('[data-symbol-type="tool"]').exists()).toBe(true)
  })

  it('renders Intent Profile as a structured planning artifact', async () => {
    const runtimeStore = new RunRuntimeStore('run_1')
    runtimeStore.apply({ ...runtimeEvent(1, 'planner.started') })
    runtimeStore.apply({ ...runtimeEvent(2, 'planner.stage.started'), payload: { stage: 'intent_profile', callKey: 'intent-profile' } })
    runtimeStore.apply({
      ...runtimeEvent(3, 'planner.profile.resolved'),
      payload: { constraintCount: 13, requiredCapabilityCount: 4, expectedArtifactCount: 2 }
    })

    const wrapper = mountEditor({ runtimeObservation: observation([]), runtimeStore })
    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')
    const intentProfile = wrapper.findAll('[data-symbol-type="stage"]').find(item => item.text().includes('Intent Profile'))!
    await intentProfile.find('.run-symbol__main').trigger('click')

    const artifact = wrapper.get('[data-testid="intent-profile-artifact"]')
    expect(artifact.text()).toContain('任务意图画像')
    expect(artifact.text()).toContain('13')
    expect(artifact.text()).toContain('4')
    expect(artifact.text()).toContain('2')
    expect(artifact.text()).toContain('Task Plan')
    expect(wrapper.get('[aria-label="Run document breadcrumb"]').text().match(/Intent Profile/g)).toHaveLength(1)
    expect(intentProfile.find('[data-symbol-type="result"]').exists()).toBe(false)
  })

  it('renders the remaining planning stages as dedicated artifacts', async () => {
    const runtimeStore = new RunRuntimeStore('run_1')
    runtimeStore.apply({ ...runtimeEvent(1, 'planner.started') })
    runtimeStore.apply({ ...runtimeEvent(2, 'planner.plan.parsed'), payload: {
      taskCount: 2, dependencyCount: 1,
      nodes: [
        { key: 'research', title: 'Research', objective: 'Collect evidence', capabilityRequirements: ['analysis'], acceptanceCriteria: ['Sources verified'] },
        { key: 'report', title: 'Report', objective: 'Write report', capabilityRequirements: ['artifact_generation'], acceptanceCriteria: ['Report delivered'] }
      ],
      relations: [{ sourceKey: 'research', targetKey: 'report', relationType: 'depends_on' }]
    } })
    const wrapper = mountEditor({ runtimeStore })

    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')
    const taskPlan = wrapper.findAll('[data-symbol-type="stage"]').find(item => item.text().includes('Task Plan'))!
    await taskPlan.find('.run-symbol__main').trigger('click')
    expect(wrapper.get('[data-testid="planning-task-plan-artifact"]').text()).toContain('6')
    expect(wrapper.get('[data-testid="planning-task-plan-artifact"]').text()).toContain('8')
    expect(taskPlan.find('[data-symbol-type="result"]').exists()).toBe(false)

    const detail = wrapper.findAll('[data-symbol-type="stage"]').find(item => item.text().includes('Detail'))!
    await detail.find('.run-symbol__main').trigger('click')
    expect(wrapper.get('[data-testid="planning-detail-artifact"]').text()).toContain('任务细化')
    expect(wrapper.get('[data-testid="planning-detail-artifact"]').text()).toContain('Collect evidence')
    expect(wrapper.get('[data-testid="planning-detail-artifact"]').text()).toContain('Sources verified')

    const relations = wrapper.findAll('[data-symbol-type="stage"]').find(item => item.text().includes('Relations'))!
    await relations.find('.run-symbol__main').trigger('click')
    expect(wrapper.get('[data-testid="planning-relations-artifact"]').text()).toContain('依赖关系')
    expect(wrapper.get('[data-testid="planning-relations-artifact"]').text()).toContain('Research')
    expect(wrapper.get('[data-testid="planning-relations-artifact"]').text()).toContain('Report')
  })

  it('shows the latest planner phase note while planning is still running', () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        traceEvent('e1', { planningProgress: true, category: 'planner', kind: 'started' }),
        traceEvent('e2', {
          planningProgress: true, category: 'planner', kind: 'stage_started',
          stage: 'relations', status: 'started', attempt: 1
        })
      ])
    })

    expect(wrapper.find('.run-progress-group__note').text()).toContain('依赖构建开始')
    expect(wrapper.text()).toContain('RUNNING')
  })

  it('keeps a failed planner group failed without inventing success', () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        traceEvent('e1', { planningProgress: true, category: 'planner', kind: 'started' }),
        traceEvent('e2', {
          planningProgress: true, category: 'planner', kind: 'failed',
          errorCode: 'ACGPlanningError', safeSummary: 'ACGPlanningError during planning'
        })
      ])
    })

    expect(wrapper.text()).toContain('规划失败')
    expect(wrapper.text()).toContain('错误码 ACGPlanningError')
    expect(wrapper.text()).not.toContain('ACGPlanningError during planning'.slice(0, 0) + '规划完成')
  })

  it('renders task groups expanded while running and collapsed with duration once done', async () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        ...plannerEvents(),
        traceEvent('t1', { status: 'started' }, { stepId: 'node_a', eventType: 'step_started' }),
        traceEvent('t2', { status: 'succeeded' }, { stepId: 'node_a', eventType: 'step_succeeded', durationMs: 18000 }),
        traceEvent('t3', { status: 'started' }, { stepId: 'node_b', eventType: 'step_started' }),
        traceEvent('t4', { tool: 'contract_reader', name: 'Read File', status: 'succeeded', latencyMs: 821 }, { stepId: 'node_b', eventType: 'tool_called' })
      ])
    })

    const groups = wrapper.findAll('.run-progress-group')
    expect(groups).toHaveLength(4)
    // running 的任务排在最前，已完成任务收起为摘要行
    const running = groups.find(node => node.text().includes('架构设计'))!
    const done = groups.find(node => node.text().includes('需求分析'))!
    expect(running.classes()).toContain('is-open')
    expect(running.text()).toContain('Running')
    expect(wrapper.findAll('.run-progress-tool')).toHaveLength(1)
    expect(wrapper.text()).toContain('Read File')
    expect(wrapper.text()).toContain('821 ms')
    expect(done.classes()).not.toContain('is-open')
    expect(done.text()).toContain('18s')
  })

  it('preserves manual expansion across polling updates and repeated clicks', async () => {
    const wrapper = mountEditor({
      runtimeObservation: observation(plannerEvents())
    })
    await wrapper.find('.run-progress-group__head').trigger('click')
    expect(wrapper.find('.run-progress-group').classes()).toContain('is-open')

    // 新一轮 polling 追加事件：用户手动展开的组不得被重新折叠
    await wrapper.setProps({
      runtimeObservation: observation([...plannerEvents(), traceEvent('e9', { planningProgress: true, category: 'planner', kind: 'retry', stage: 'outline', status: 'retrying', attempt: 1, retryCount: 1, errorCode: 'MODEL_TIMEOUT' })])
    })
    expect(wrapper.find('.run-progress-group').classes()).toContain('is-open')

    await wrapper.find('.run-progress-group__head').trigger('click')
    expect(wrapper.find('.run-progress-group').classes()).toContain('is-open')
  })

  it('selects the semantic task without forcing an editor switch', async () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        ...plannerEvents(),
        traceEvent('t1', { status: 'started' }, { stepId: 'node_a', eventType: 'step_started' })
      ])
    })

    await wrapper.get('[data-symbol-type="task"] .run-symbol__main').trigger('click')
    const emitted = wrapper.emitted('selectSemanticTask')
    expect(emitted).toBeTruthy()
    expect(emitted!.at(-1)).toEqual(['requirements.analysis'])
  })

  it('shows the graph beside the outline and opens artifacts through the existing channel', async () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        ...plannerEvents(),
        traceEvent('t1', { status: 'started' }, { stepId: 'node_a', eventType: 'step_started' })
      ])
    })

    const acg = wrapper.get('[data-symbol-type="acg"]')
    await acg.find('.run-symbol__main').trigger('click')
    expect(wrapper.find('[data-testid="acg-preview"]').exists()).toBe(true)
    expect(wrapper.find('.run-progress-result__action').exists()).toBe(false)
    expect(wrapper.emitted('locateGraph')).toBeUndefined()

    await wrapper.get('[data-symbol-type="result"] .run-symbol__main').trigger('click')
    const stepArtifact = wrapper.get('[data-symbol-type="artifact"]')
    await stepArtifact.find('.run-progress-artifact__open').trigger('click')
    expect(wrapper.emitted('openArtifact')![0][0]).toMatchObject({ kind: 'artifact', artifactId: 'art_1' })

    await wrapper.find('.run-progress-artifact__open').trigger('click')
    expect(wrapper.emitted('openArtifact')!.at(-1)![0]).toMatchObject({ kind: 'artifact', artifactId: 'art_1' })
  })

  it('passes persisted step states of the observed run to the topology graph', async () => {
    const value = observation([], 'running')
    value.run = { runId: 'run_1', missionId: 'mission_1', workflowId: 'workflow', domain: 'test', status: 'running',
      steps: [
        { stepId: 'node_a', name: '需求分析', agentName: 'agent.a', status: 'completed' },
        { stepId: 'node_b', name: '架构设计', agentName: 'agent.b', status: 'waiting_review' }
      ],
      completedStepIds: ['node_a'], activeStepIds: ['node_b'] }
    const wrapper = mountEditor({ runtimeObservation: value })

    const acg = wrapper.get('[data-symbol-type="acg"]')
    await acg.find('.run-symbol__main').trigger('click')
    const stub = wrapper.findComponent(topologyStub)
    expect(stub.props('stepStates').map((state: { stepId: string; status: string }) => [state.stepId, state.status]))
      .toEqual([['node_a', 'completed'], ['node_b', 'waiting_review']])
    expect(stub.props('completedStepIds')).toEqual(['node_a'])
  })

  it('renders legacy planningProgress events with engineering wording', () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        traceEvent('legacy_1', { planningProgress: true, stage: 'intent_profile', status: 'started' })
      ])
    })

    expect(wrapper.text()).toContain('意图解析开始')
    expect(wrapper.text()).not.toContain('正在理解')
  })

  it('renders live planner stream facts before Trace projection catches up', async () => {
    const runtimeStore = new RunRuntimeStore('run_1')
    runtimeStore.apply(runtimeEvent(1, 'planner.started'))
    runtimeStore.apply({ ...runtimeEvent(2, 'planner.stage.started'), payload: { stage: 'outline', callKey: 'outline' } })
    runtimeStore.apply({ ...runtimeEvent(3, 'planner.model.first_token'), payload: { elapsedMs: 83 } })
    runtimeStore.apply({ ...runtimeEvent(4, 'planner.model.activity'), payload: { elapsedMs: 102, idleMs: 5, receivedChunks: 4, receivedLength: 28 } })
    runtimeStore.apply({ ...runtimeEvent(5, 'planner.model.output.delta'), payload: { stage: 'outline', callKey: 'outline', delta: '{"tasks":["draft"]}' } })
    runtimeStore.apply({ ...runtimeEvent(6, 'planner.profile.resolved'), payload: { requiredCapabilityCount: 2, expectedArtifactCount: 1 } })
    runtimeStore.apply({ ...runtimeEvent(7, 'planner.draft.updated'), payload: {
      stage: 'detail',
      nodes: [
        { key: 'understand', title: '理解任务', capabilityId: 'task_understanding', status: 'detailed', rationale: '先建立约束基线' },
        { key: 'analyze', title: '分析方案', capabilityId: 'analysis', status: 'outlined', rationale: '' },
      ],
      edges: [{ sourceKey: 'understand', targetKey: 'analyze', relationType: 'depends_on' }],
    } })

    const wrapper = mountEditor({ runtimeObservation: observation([]), runtimeStore })

    expect(wrapper.get('.run-progress__status').text()).toBe('RUNNING')
    expect(wrapper.text()).toContain('生成任务骨架')
    expect(wrapper.text()).toContain('模型响应中')
    expect(wrapper.text()).toContain('Attempt 1')
    expect(wrapper.text()).toContain('1 chunks')
    expect(wrapper.text()).toContain('102 ms')
    expect(wrapper.get('[data-testid="planner-live-output"]').text()).toContain('draft')
    expect(wrapper.text()).toContain('1 chunks')
    const acg = wrapper.get('[data-symbol-type="acg"]')
    expect(acg.text()).toContain('ACG')
    await acg.find('.run-symbol__main').trigger('click')
    expect(wrapper.find('[data-symbol-type="acg-node"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="planner-growing-graph"]').exists()).toBe(false)
    await wrapper.get('[data-symbol-type="planner"] .run-symbol__main').trigger('click')
    const intentProfile = wrapper.findAll('[data-symbol-type="stage"]').find(item => item.text().includes('Intent Profile'))!
    await intentProfile.find('.run-symbol__main').trigger('click')
    const artifact = wrapper.get('[data-testid="intent-profile-artifact"]')
    expect(artifact.text()).toContain('2')
    expect(artifact.text()).toContain('1')
  })

  it('never renders reasoning, prompt or raw json markers', () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([
        traceEvent('sec_1', {
          planningProgress: true, category: 'planner', kind: 'started',
          prompt: 'SECRET_PROMPT_MARKER', reasoning: 'SECRET_REASONING_MARKER', modelOutput: 'RAW_JSON_MARKER'
        })
      ])
    })

    const html = wrapper.html()
    expect(html).not.toContain('SECRET_PROMPT_MARKER')
    expect(html).not.toContain('SECRET_REASONING_MARKER')
    expect(html).not.toContain('RAW_JSON_MARKER')
  })

  it('shows the empty state without a run instead of pretending progress', () => {
    const wrapper = mountEditor({ runId: null })

    expect(wrapper.find('.run-progress__status').text()).toBe('尚未运行')
    expect(wrapper.find('.run-progress__status').classes()).toContain('is-idle')
    expect(wrapper.text()).toContain('运行开始后，这里会显示任务规划和执行过程。')
    expect(wrapper.text()).not.toContain('等待模型思考')
  })

  it('does not pretend an unobserved run is still running', () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([], null),
      projection: projection({ runs: [] } as Partial<MissionWorkspaceProjection>)
    })

    expect(wrapper.find('.run-progress__status').text()).toBe('状态未知')
    expect(wrapper.find('.run-progress__status').classes()).toContain('is-unknown')
    expect(wrapper.text()).not.toContain('RUNNING')
  })

  it('does not treat an unsupported persisted status as active', () => {
    const wrapper = mountEditor({
      runtimeObservation: observation([], 'mystery_status'),
      projection: projection({ runs: [{ runId: 'run_1', status: 'mystery_status', createdAt: '', completedAt: null, isActive: false }] } as Partial<MissionWorkspaceProjection>)
    })

    expect(wrapper.find('.run-progress__status').text()).toBe('状态未知')
    expect(wrapper.text()).not.toContain('RUNNING')
  })

  it('resolves the run id from a historical run entry itself', () => {
    const wrapper = mountEditor({
      entry: entry({ entryId: 'run_run_9', kind: 'run', name: 'run_9', status: 'failed', runId: 'run_9' }),
      runId: null,
      projection: projection({
        runs: [{ runId: 'run_9', status: 'failed', createdAt: '2026-09-02T00:00:00Z', completedAt: '2026-09-02T00:02:14Z', isActive: false }]
      } as Partial<MissionWorkspaceProjection>),
      runtimeObservation: observation(plannerEvents(), 'failed')
    })

    expect(wrapper.text()).toContain('run_9')
    expect(wrapper.text()).toContain('运行失败')
  })

  it('disables follow-latest on manual scroll up and restores it from the button', async () => {
    const wrapper = mountEditor()
    const body = wrapper.find('.run-progress__body')
    const element = body.element as HTMLElement
    Object.defineProperty(element, 'scrollHeight', { value: 2000, configurable: true })
    Object.defineProperty(element, 'scrollTop', { value: 100, configurable: true, writable: true })
    Object.defineProperty(element, 'clientHeight', { value: 400, configurable: true })

    await body.trigger('scroll')
    expect(wrapper.find('.run-progress__follow').exists()).toBe(true)

    await wrapper.find('.run-progress__follow').trigger('click')
    expect(wrapper.find('.run-progress__follow').exists()).toBe(false)
  })
})
