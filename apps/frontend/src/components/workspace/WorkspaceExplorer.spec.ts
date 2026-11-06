import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import WorkspaceExplorer from './WorkspaceExplorer.vue'
import type { MissionWorkspaceProjection, WorkspaceEntry } from '@/services/api/agentos'

const projection = (): MissionWorkspaceProjection => ({
  mission: { missionId: 'mission_1', userId: 'user_1', goal: '设备人员规划', description: '', metadata: {}, createdAt: '2026-08-28T00:00:00Z', updatedAt: '2026-08-28T00:00:00Z', status: 'created' },
  activeRun: { runId: 'run_2', status: 'running', createdAt: '2026-08-28T00:02:00Z', isActive: true },
  runs: [],
  graphNodes: [],
  diagnostics: [],
  entries: [
    { entryId: 'folder:overview', kind: 'folder', name: 'Overview', group: 'overview', displayOrder: 0 },
    { entryId: 'folder:steps', kind: 'folder', name: 'Steps', group: 'steps', displayOrder: 0 },
    { entryId: 'folder:output', kind: 'folder', name: 'Output', group: 'output', displayOrder: 0 },
    { entryId: 'folder:runs', kind: 'folder', name: 'Runs', group: 'runs', displayOrder: 0 },
    { entryId: 'overview:graph.acg', kind: 'graph', name: 'graph.acg', group: 'overview', displayOrder: 0 },
    { entryId: 'overview:mission.md', kind: 'virtual_document', name: 'mission.md', group: 'overview', displayOrder: 1, content: '# Mission' },
    { entryId: 'task:capacity', kind: 'task', name: 'Capacity planning', group: 'steps', displayOrder: 0, semanticTaskKey: 'capacity', taskId: 'task_capacity', status: 'completed', attemptCount: 1, artifactCount: 1, identityQuality: 'canonical' },
    { entryId: 'task:capacity:primary', kind: 'artifact', name: 'capacity.md', group: 'steps', displayOrder: 0, parentEntryId: 'task:capacity', semanticTaskKey: 'capacity', artifactKey: 'primary', identityQuality: 'canonical' },
    { entryId: 'run:run_1', kind: 'run', name: 'run_1', group: 'runs', displayOrder: 0, runId: 'run_1', status: 'succeeded' },
    { entryId: 'run:run_2', kind: 'run', name: 'run_2', group: 'runs', displayOrder: 1, runId: 'run_2', status: 'running', isActive: true }
  ]
})

const mountExplorer = (overrides: Partial<MissionWorkspaceProjection> = {}) => mount(WorkspaceExplorer, {
  props: { projection: { ...projection(), ...overrides }, activeEditorId: null, selectedRunId: 'run_2' },
  global: { stubs: { 'el-icon': true } }
})

describe('WorkspaceExplorer', () => {
  it('shows the current formal goal and its revision instead of Identity goal', () => {
    const wrapper = mountExplorer({ missionDisplay: { objective: 'current goal', sourceType: 'SEMANTIC' },
      missionSemanticView: { missionId: 'mission_1', semanticStatus: 'INITIALIZED', missionRevision: 2,
        objective: 'current goal', constraints: [], sourceReferences: [], sourceStatus: 'NOT_APPLICABLE' } })
    expect(wrapper.text()).toContain('current goal')
    expect(wrapper.text()).toContain('revision 2')
    expect(wrapper.text()).not.toContain('设备人员规划')
  })
  it('renders Explorer, Runs, Tasks and Artifacts without a global mission list', () => {
    const wrapper = mountExplorer()
    expect(wrapper.findAll('.workspace-tree__section')).toHaveLength(4)
    expect(wrapper.text()).toContain('EXPLORER')
    expect(wrapper.text()).toContain('TASKS')
    expect(wrapper.text()).toContain('ARTIFACTS')
    expect(wrapper.text()).toContain('RUNS')
    expect(wrapper.text()).not.toContain('所有 Mission')
  })

  it('opens a graph, virtual document, and artifact by entry kind', async () => {
    const wrapper = mountExplorer()
    const entries = wrapper.findAll('.workspace-tree__entry')
    await entries.find(item => item.text().includes('graph.acg'))?.trigger('click')
    await entries.find(item => item.text().includes('mission.md'))?.trigger('click')
    await entries.find(item => item.text().includes('capacity.md'))?.trigger('click')
    expect(wrapper.emitted('open')?.map(args => args[0].kind)).toEqual(['graph', 'virtual_document', 'artifact'])
  })

  it('renders Task entries as the Steps count and keeps Artifact as a child', async () => {
    const wrapper = mountExplorer()
    const steps = wrapper.findAll('.workspace-tree__section-toggle').find(item => item.text().includes('TASKS'))
    expect(steps?.text()).toContain('1')
    expect(wrapper.find('.workspace-tree__entry--child').text()).toContain('capacity.md')
    await wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('Capacity planning'))?.trigger('click')
    expect(wrapper.emitted('open')?.at(-1)?.[0].kind).toBe('task')
  })

  it('routes Run entries through Run selection instead of opening them against another projection', async () => {
    const wrapper = mountExplorer()
    await wrapper.findAll('.workspace-tree__entry').find(item => item.text().includes('run_2'))!.trigger('click')
    expect(wrapper.emitted('selectRun')).toEqual([['run_2']])
    expect(wrapper.emitted('open')).toBeUndefined()
  })

  it('keeps projection diagnostics out of the Explorer chrome', () => {
    const wrapper = mountExplorer({ diagnostics: [{ code: 'PLAN_SNAPSHOT_UNRESOLVED', message: '历史结构不可确定', severity: 'warning' }] })
    expect(wrapper.find('.workspace-explorer__diagnostics').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('PLAN_SNAPSHOT_UNRESOLVED')
  })
})

describe('WorkspaceExplorer drag ordering', () => {
  const ORDER_KEY = 'zhiyi.mission.workspace.explorer.order.v1'
  const readOrderStore = () => JSON.parse(localStorage.getItem(ORDER_KEY) || '{}')
  const stepRows = (wrapper: ReturnType<typeof mountExplorer>) => (
    wrapper.findAll('.workspace-tree__section').find(section => section.text().includes('TASKS'))!
      .findAll('.workspace-tree__entry')
  )
  const dragTaskRow = (id: string, displayOrder: number): WorkspaceEntry => ({
    entryId: id, kind: 'task', name: id.replace('task:', ''), group: 'steps', displayOrder,
    semanticTaskKey: id.replace('task:', ''), status: 'completed', identityQuality: 'canonical'
  })
  const mountDragExplorer = (extraTasks: WorkspaceEntry[] = []) => mountExplorer({
    entries: [
      ...projection().entries.filter(entry => entry.group !== 'steps'),
      dragTaskRow('task:a', 0),
      dragTaskRow('task:b', 1),
      dragTaskRow('task:c', 2),
      ...extraTasks
    ]
  })

  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('reorders task rows by dragging and persists the visual snapshot for the mission+run', async () => {
    const wrapper = mountDragExplorer()
    const rows = () => stepRows(wrapper)
    expect(rows().map(row => row.attributes('title'))).toEqual(['a', 'b', 'c'])
    expect(rows().map(row => row.find('.workspace-tree__order').text())).toEqual(['01', '02', '03'])

    await rows()[0].trigger('dragstart')
    // jsdom 矩形为 0×0 且合成事件不带坐标：显式传 clientY=0，落点=中点 → 判「插到目标行之后」。
    await rows()[2].trigger('dragover', { clientY: 0 })
    await rows()[2].trigger('drop')
    expect(rows().map(row => row.attributes('title'))).toEqual(['b', 'c', 'a'])
    // 徽标跟随视觉顺序重编号，而不是后端 displayOrder。
    expect(rows().map(row => row.find('.workspace-tree__order').text())).toEqual(['01', '02', '03'])
    expect(readOrderStore().stepsOrders['mission_1|run_2']).toEqual(['task:b', 'task:c', 'task:a'])
  })

  it('restores the persisted order on remount and appends unseen tasks by displayOrder', async () => {
    localStorage.setItem(ORDER_KEY, JSON.stringify({ stepsOrders: { 'mission_1|run_2': ['task:c', 'task:a'] } }))
    const wrapper = mountDragExplorer([dragTaskRow('task:d', 3)])
    expect(stepRows(wrapper).map(row => row.attributes('title'))).toEqual(['c', 'a', 'b', 'd'])
    expect(stepRows(wrapper).map(row => row.find('.workspace-tree__order').text())).toEqual(['01', '02', '03', '04'])
  })

  it('reorders sections by dragging their headers and persists the global order', async () => {
    const wrapper = mountExplorer()
    const headerTexts = () => wrapper.findAll('.workspace-tree__section-toggle').map(header => header.text())
    expect(headerTexts()[0]).toContain('EXPLORER')

    const headers = wrapper.findAll('.workspace-tree__section-toggle')
    await headers[0].trigger('dragstart')
    await headers[3].trigger('dragover', { clientY: 0 })
    await headers[3].trigger('drop')

    expect(headerTexts()[0]).toContain('RUNS')
    expect(headerTexts()[1]).toContain('TASKS')
    expect(headerTexts()[2]).toContain('ARTIFACTS')
    expect(headerTexts()[3]).toContain('EXPLORER')
    expect(readOrderStore().sectionOrder).toEqual(['runs', 'steps', 'output', 'overview'])
  })
})
