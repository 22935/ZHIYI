import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import { createWorkbenchRegistry } from '@/workbench/registry'
import { createWorkbenchContext } from '@/workbench/context'
import SecondarySidebar from './SecondarySidebar.vue'
import ProjectRunSidebarView from '@/workbench/contributions/project/ProjectRunSidebarView.vue'
import ResourceSidebarView from '@/workbench/contributions/resource/ResourceSidebarView.vue'
import RuntimeAuditSidebarView from '@/workbench/contributions/runtime/RuntimeAuditSidebarView.vue'
import RuntimeCommunicationSidebarView from '@/workbench/contributions/runtime/RuntimeCommunicationSidebarView.vue'
import RuntimeContextSidebarView from '@/workbench/contributions/runtime/RuntimeContextSidebarView.vue'
import type { WorkbenchContext } from '@/workbench/types'
import type { WorkspaceEntry, WorkspaceGraphNode } from '@/services/api/agentos'
import { projectLifecycle } from '@/workbench/runtime/lifecycleProjection'
import { capabilitiesFixture } from '@/test/fixtures/runCapabilities'

const graphEntry: WorkspaceEntry = {
  entryId: 'overview:graph.acg',
  kind: 'graph',
  name: 'graph.acg',
  group: 'overview',
  displayOrder: 0,
  graphId: 'graph_1',
  graphVersion: 1
}

const taskEntry: WorkspaceEntry = {
  entryId: 'task:capacity',
  kind: 'task',
  name: 'Capacity',
  group: 'steps',
  displayOrder: 0,
  semanticTaskKey: 'capacity',
  taskId: 'task_capacity',
  objective: 'Form a capacity plan',
  dependencyKeys: ['scope'],
  status: 'completed',
  attemptCount: 1,
  latestAttemptId: 'attempt_capacity',
  artifactCount: 2,
  acgNodeId: 'node_capacity',
  identityQuality: 'canonical'
}

const artifactEntry: WorkspaceEntry = {
  entryId: 'task:capacity:primary',
  kind: 'artifact',
  name: 'primary.md',
  group: 'steps',
  displayOrder: 0,
  semanticTaskKey: 'capacity',
  artifactKey: 'primary',
  artifactId: 'artifact_1',
  contentRef: 'manifest_1',
  attemptId: 'attempt_capacity',
  runId: 'run_1',
  identityQuality: 'canonical'
}

const node: WorkspaceGraphNode = {
  acgNodeId: 'node_capacity',
  nodeType: 'step',
  name: 'Capacity',
  semanticTaskKey: 'capacity',
  taskId: 'task_capacity',
  displayOrder: 0,
  status: 'completed',
  attemptId: 'attempt_capacity',
  artifactCount: 2,
  identityQuality: 'canonical'
}

const baseContext = (): WorkbenchContext => createWorkbenchContext({
  missionId: 'mission_1',
  runId: 'run_1',
  activeEditorId: graphEntry.entryId,
  activeEntryKind: 'graph',
  runtimeObservation: runtimeObservation('run_1')
})

const runtimeObservation = (runId: string): RuntimeObservation => ({
  runId,
  runStatus: 'succeeded',
  traces: [],
  events: [],
  communication: [],
  toolCalls: [],
  problems: [],
  audit: {
    provenanceStatus: null,
    provenanceRecordCount: 0,
    evidenceCount: 0,
    contractViolationCount: 0,
    recoveryCount: 0,
    reviewCount: null
  },
  provenance: {
    schemaVersion: null,
    integrityStatus: null,
    productions: [],
    consumptions: [],
    interactions: []
  },
  operational: null,
  recoveryTrace: [],
  contractViolations: [],
  scheduleTrace: [],
  patchRefs: [],
  lowEntropy: {
    observed: false,
    source: null,
    averageSavingRatio: null,
    effectiveSavingRatio: null,
    tokensAvailable: null,
    tokensDelivered: null,
    tokensSaved: null,
    recoveryCount: 0,
    degradationCount: 0,
    interactionCount: 0,
    contractViolationCount: 0,
    integrityStatus: null
  },
  resourceObservation: null,
  contextPacks: null,
  unavailableSources: []
})

const inspectorContext = (overrides: Partial<{
  context: WorkbenchContext
  entry: WorkspaceEntry | null
  graphNode: WorkspaceGraphNode | null
}> = {}) => ({
  ...(overrides.context || baseContext()),
  entry: overrides.entry === undefined ? graphEntry : overrides.entry,
  graphNode: overrides.graphNode === undefined ? null : overrides.graphNode,
  available: true,
  graph: { graphId: 'graph_1', nodes: [], edges: [], metadata: { graphVersion: 1 } },
  runStatus: 'succeeded'
})

const viewProps = (context: ReturnType<typeof inspectorContext>) => ({
  entry: context.entry,
  graphNode: context.graphNode,
  graphNodes: [node],
  available: context.available,
  runId: context.runId,
  missionId: context.missionId,
  graph: context.graph,
  runStatus: context.runStatus,
  historical: context.historicalMode,
  resourceObservation: context.runtimeObservation?.resourceObservation || null,
  runtimeObservation: context.runtimeObservation
})

const createSecondaryRegistry = () => createWorkbenchRegistry().register({
  id: 'native-secondary-sidebar',
  secondarySidebarViews: [
    { id: 'project.run-view', title: '运行', order: 100, component: ProjectRunSidebarView, when: () => true },
    { id: 'resource.view', title: '资源', order: 200, component: ResourceSidebarView, when: () => true },
    { id: 'runtime.communication-view', title: '通信', order: 300, component: RuntimeCommunicationSidebarView, when: () => true },
    { id: 'runtime.audit-view', title: '审计', order: 400, component: RuntimeAuditSidebarView, when: () => true },
    { id: 'runtime.context-view', title: '上下文', order: 500, component: RuntimeContextSidebarView, when: () => true }
  ]
})

const mountSidebar = (overrides: Partial<{
  context: WorkbenchContext
  entry: WorkspaceEntry | null
  graphNode: WorkspaceGraphNode | null
  historical: boolean
  runId: string | null
}> = {}) => {
  const context = inspectorContext({
    context: overrides.context,
    entry: overrides.entry,
    graphNode: overrides.graphNode
  })
  return mount(SecondarySidebar, {
    props: {
      registry: createSecondaryRegistry(),
      context,
      title: context.entry?.name || 'Mission',
      historical: overrides.historical || false,
      componentProps: viewProps(context)
    }
  })
}

describe('SecondarySidebar', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('resolves the five native views and defaults to Run', () => {
    const registry = createSecondaryRegistry()
    const context = {
      ...baseContext(),
      entry: graphEntry,
      graphNode: null,
      available: true,
      graph: null,
      runStatus: 'succeeded'
    }
    expect(registry.resolveSecondarySidebarViews(context).map(view => view.title)).toEqual(['运行', '资源', '通信', '审计', '上下文'])
    const wrapper = mountSidebar()
    expect(wrapper.find('.secondary-sidebar__tabs button.is-active').text()).toBe('运行')
    expect(wrapper.text()).toContain('执行图概览')
  })

  it('restores low-entropy metrics and runtime content in the Run view', () => {
    const observed = {
      ...runtimeObservation('run_1'),
      traces: [{
        eventId: 'trace_1', runId: 'run_1', stepId: 'node_capacity', eventType: 'step_completed',
        observation: '运行内容已记录', timestamp: '2026-08-29T00:01:00Z', durationMs: null,
        status: 'completed', payload: {}, source: 'trace' as const
      }],
      events: [{
        eventId: 'event_1', eventType: 'step_completed', timestamp: '2026-08-29T00:01:00Z',
        stepId: 'node_capacity', target: 'node_capacity', summary: '运行内容已记录', source: 'trace' as const
      }],
      communication: [{
        id: 'communication_1', source: 'provenance' as const, sourceEventId: 'event_2',
        timestamp: '2026-08-29T00:01:00Z', producerStepId: 'node_a', consumerStepId: 'node_capacity',
        artifactRef: null, fields: [], tokenCount: 400, status: 'valid', summary: 'node_a → node_capacity'
      }],
      toolCalls: [{
        eventId: 'tool_1', tool: 'search', name: 'search', stepId: 'node_capacity', status: 'succeeded',
        startedAt: '2026-08-29T00:01:00Z', durationMs: null, latencyMs: 42, source: 'trace' as const
      }],
      lowEntropy: {
        observed: true, source: 'provenance' as const, averageSavingRatio: 0.6, effectiveSavingRatio: 0.6,
        tokensAvailable: 1000, tokensDelivered: 400, tokensSaved: 600, recoveryCount: 0, degradationCount: 0,
        interactionCount: 1, contractViolationCount: 0, integrityStatus: 'verified'
      },
      provenance: {
        schemaVersion: null,
        integrityStatus: 'verified',
        productions: [{ eventId: 'production_1', producerStepId: 'node_a', fieldNames: ['brief'], evidenceRefs: ['evidence_1'] }],
        consumptions: [{ eventId: 'consumption_1', producerStepIds: ['node_a'], consumerStepId: 'node_capacity', consumedFields: ['brief'], contractStatus: 'valid' }],
        interactions: [{
          interactionId: 'interaction_1', eventId: 'interaction_event_1', edgeIds: [], producerStepIds: ['node_a'],
          consumerStepId: 'node_capacity', producerAgentNames: ['agent_a'], consumerAgentName: 'agent_capacity',
          fieldsByProducer: { node_a: ['brief'] }, tokensDelivered: 400, tokensAvailable: 1000,
          savingRatio: 0.6, evidenceRefs: ['evidence_1'], contractStatus: 'valid'
        }]
      },
      operational: {
        lineage: {},
        nodeExecutions: [{
          operationId: 'operation_1', executionInstanceId: 'execution_1', runId: 'run_1', stepId: 'node_capacity',
          attemptId: 'attempt_capacity', phase: 'committed', artifactRefs: { primary: 'artifact_1' },
          auditRef: 'audit_1', commitId: 'commit_1', loopPath: [1], failureCode: null
        }],
        controlFrames: [{ frameId: 'frame_1', type: 'parallel', status: 'joined' }],
        communicationRefs: ['communication_ref_1'],
        memoryRefs: ['memory_ref_1'],
        evidenceRefs: ['evidence_1'],
        leaseStatuses: { agent_capacity: 'released' },
        loopIterations: { node_capacity: 1 },
        consensusResults: { node_capacity: { decision: 'accepted' } },
        debateSessions: { node_capacity: { rounds: 2 } },
        recoveryOutcome: { strategy: 'checkpoint', status: 'recovered' }
      },
      recoveryTrace: [{
        eventId: 'recovery_1', runId: 'run_1', stepId: 'node_capacity', eventType: 'run_recovered',
        observation: '从检查点恢复', timestamp: '2026-08-29T00:05:00Z', durationMs: null,
        status: 'recovered', payload: { strategy: 'checkpoint' }, source: 'trace'
      }],
      contractViolations: [],
      scheduleTrace: [{
        eventId: 'schedule_1', runId: 'run_1', stepId: 'node_capacity', eventType: 'schedule_batch_joined',
        observation: '调度批次已汇合', timestamp: '2026-08-29T00:04:00Z', durationMs: null,
        status: 'completed', payload: {}, source: 'trace'
      }],
      patchRefs: ['patch_1']
    }
    const context = inspectorContext({
      context: createWorkbenchContext({ ...baseContext(), runtimeObservation: observed })
    })
    const wrapper = mountSidebar({ context })

    expect(wrapper.text()).toContain('上下文传递')
    expect(wrapper.text()).toContain('60.0%')
    expect(wrapper.text()).toContain('600')
    expect(wrapper.text()).toContain('执行记录')
    expect(wrapper.text()).toContain('运行内容已记录')
    expect(wrapper.text()).toContain('工具调用')
  })

  it('switches views and persists only the selected view id', async () => {
    const wrapper = mountSidebar()
    for (const [label, content] of [['资源', '运行资源'], ['通信', '通信摘要'], ['审计', '审计状态'], ['上下文', '上下文数据']]) {
      await wrapper.findAll('.secondary-sidebar__tabs button').find(button => button.text() === label)?.trigger('click')
      expect(wrapper.find('.secondary-sidebar__tabs button.is-active').text()).toBe(label)
      expect(wrapper.text()).toContain(content)
    }
    expect(localStorage.getItem('zhiyi.mission.workspace.secondary-sidebar.view.v1')).toBe('runtime.context-view')
    expect(localStorage.getItem('zhiyi.mission.workspace.secondary-sidebar.view.v1')).not.toContain('run_1')
  })

  it('forwards the verified final delivery from the run view to the workspace', async () => {
    const delivery = { ...artifactEntry, artifactKey: 'final', artifactType: 'run_deliverable' }
    const summary = { runId: 'run_1', status: 'completed', createdAt: '2026-11-08',
      actionCapabilities: capabilitiesFixture('run_1', 'mission_1', 'completed', 38) }
    const lifecycle = projectLifecycle({ selectedRunId: 'run_1', workspace: {
      mission: { missionId: 'mission_1' }, activeRun: summary, runs: [summary], entries: [delivery],
      graphNodes: [], diagnostics: []
    } as any })
    const context = createWorkbenchContext({ ...baseContext(), lifecycle })
    const wrapper = mountSidebar({ context, entry: delivery })
    await wrapper.get('.lifecycle-delivery button').trigger('click')
    expect(wrapper.emitted('openArtifact')).toEqual([[delivery]])
    wrapper.unmount()
  })

  it('supports keyboard tab navigation with one focusable tab and a labelled panel', async () => {
    const wrapper = mountSidebar()
    const tabs = wrapper.findAll('[role="tab"]')
    expect(tabs.filter(tab => tab.attributes('tabindex') === '0')).toHaveLength(1)
    await tabs[0].trigger('keydown', { key: 'ArrowRight' })
    expect(wrapper.get('[aria-selected="true"]').text()).toBe('资源')
    expect(wrapper.get('[role="tabpanel"]').attributes('aria-labelledby')).toBe('inspector-tab-resource.view')
    await wrapper.get('[aria-selected="true"]').trigger('keydown', { key: 'End' })
    expect(wrapper.get('[aria-selected="true"]').text()).toBe('上下文')
    await wrapper.get('[aria-selected="true"]').trigger('keydown', { key: 'Home' })
    expect(wrapper.get('[aria-selected="true"]').text()).toBe('运行')
    wrapper.unmount()
  })

  it('migrates all seven legacy panel data groups into the current sidebar views', async () => {
    const observed = {
      ...runtimeObservation('run_1'),
      operational: {
        lineage: {},
        nodeExecutions: [],
        controlFrames: [{ frameId: 'frame_1', status: 'joined' }],
        communicationRefs: ['communication_ref_1'],
        memoryRefs: ['memory_ref_1'],
        evidenceRefs: ['evidence_1'],
        leaseStatuses: { agent_1: 'released' },
        loopIterations: { task_1: 1 },
        consensusResults: { task_1: { decision: 'accepted' } },
        debateSessions: { task_1: { rounds: 1 } },
        recoveryOutcome: { strategy: 'checkpoint', status: 'recovered' }
      },
      provenance: {
        schemaVersion: null,
        integrityStatus: 'verified',
        productions: [{ eventId: 'production_1', producerStepId: 'step_1', fieldNames: ['brief'] }],
        consumptions: [{ eventId: 'consumption_1', producerStepIds: ['step_1'], consumerStepId: 'step_2', consumedFields: ['brief'] }],
        interactions: [{
          interactionId: 'interaction_1', eventId: 'interaction_event_1', edgeIds: [], producerStepIds: ['step_1'],
          consumerStepId: 'step_2', producerAgentNames: ['agent_1'], consumerAgentName: 'agent_2',
          fieldsByProducer: { step_1: ['brief'] }, tokensDelivered: 40, tokensAvailable: 100, savingRatio: 0.6,
          evidenceRefs: [], contractStatus: 'valid'
        }]
      },
      recoveryTrace: [{
        eventId: 'recovery_1', runId: 'run_1', stepId: 'step_1', eventType: 'run_recovered', observation: 'recovered',
        timestamp: '2026-08-29T00:00:00Z', durationMs: null, status: 'succeeded', payload: { strategy: 'checkpoint' }, source: 'trace'
      }],
      contractViolations: [],
      scheduleTrace: [],
      patchRefs: ['patch_1']
    } as RuntimeObservation
    const context = inspectorContext({ context: createWorkbenchContext({ ...baseContext(), runtimeObservation: observed }) })
    const wrapper = mountSidebar({ context })

    await wrapper.findAll('.secondary-sidebar__tabs button').find(button => button.text() === '上下文')!.trigger('click')
    expect(wrapper.text()).toContain('控制协同')
    expect(wrapper.text()).toContain('frame_1')
    expect(wrapper.text()).toContain('通信上下文')
    expect(wrapper.text()).toContain('communication_ref_1')
    expect(wrapper.text()).toContain('memory_ref_1')

    await wrapper.findAll('.secondary-sidebar__tabs button').find(button => button.text() === '通信')!.trigger('click')
    expect(wrapper.text()).toContain('数据流转')
    expect(wrapper.text()).toContain('production_1')
    expect(wrapper.text()).toContain('consumption_1')
    expect(wrapper.text()).toContain('运行交互')
    expect(wrapper.text()).toContain('interaction_1')

    await wrapper.findAll('.secondary-sidebar__tabs button').find(button => button.text() === '审计')!.trigger('click')
    expect(wrapper.text()).toContain('恢复审计')
    expect(wrapper.text()).toContain('patch_1')
    expect(wrapper.text()).toContain('恢复与调度记录')
    expect(wrapper.text()).toContain('recovery_1')
  })

  it('renders task and artifact context without retaining the previous selection', async () => {
    const wrapper = mountSidebar()
    const taskContext = inspectorContext({
      context: createWorkbenchContext({
        ...baseContext(),
        activeEditorId: taskEntry.entryId,
        activeEntryKind: 'task',
        selectedSemanticTaskKey: 'capacity',
        selectedAcgNodeId: node.acgNodeId
      }),
      entry: taskEntry,
      graphNode: node
    })
    await wrapper.setProps({
      context: taskContext,
      componentProps: viewProps(taskContext)
    })
    expect(wrapper.text()).toContain('task_capacity')
    expect(wrapper.text()).toContain('attempt_capacity')

    const artifactContext = inspectorContext({
      context: createWorkbenchContext({
        ...baseContext(),
        activeEditorId: artifactEntry.entryId,
        activeEntryKind: 'artifact',
        selectedSemanticTaskKey: 'capacity',
        selectedArtifactId: 'artifact_1'
      }),
      entry: artifactEntry,
      graphNode: null
    })
    await wrapper.setProps({
      context: artifactContext,
      componentProps: viewProps(artifactContext)
    })
    expect(wrapper.text()).toContain('artifact_1')
    expect(wrapper.text()).not.toContain('task_capacity')
  })

  it('refreshes the active view when switching runs and marks historical context', async () => {
    const context = inspectorContext({
      context: createWorkbenchContext({
        ...baseContext(),
        runId: 'run_2',
        historicalMode: true,
        runtimeObservation: runtimeObservation('run_2')
      })
    })
    const wrapper = mountSidebar()
    await wrapper.setProps({
      context,
      historical: true,
      componentProps: viewProps(context)
    })
    expect(wrapper.text()).toContain('run_2')
    expect(wrapper.text()).not.toContain('run_1')
    expect(wrapper.text()).toContain('历史记录 · 只读')
    expect(wrapper.find('.secondary-sidebar__body').exists()).toBe(true)
  })
})
