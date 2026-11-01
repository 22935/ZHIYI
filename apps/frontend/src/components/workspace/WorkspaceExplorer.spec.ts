import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkspaceExplorer from './WorkspaceExplorer.vue'
import type { MissionWorkspaceProjection } from '@/services/api/agentos'

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
