import { createPinia } from 'pinia'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, afterEach, expect, it, vi } from 'vitest'
import MissionWorkspaceView from './MissionWorkspaceView.vue'
import EditorGroup from '@/components/workspace/EditorGroup.vue'
import GraphEditor from '@/components/workspace/GraphEditor.vue'
import WorkspaceViewHost from '@/components/app/WorkspaceViewHost.vue'
import { capabilitiesFixture } from '@/test/fixtures/runCapabilities'
import { agentosRequest } from '@/services/api/agentos/client'
import { agentosApi, type MissionWorkspaceProjection, type WorkflowRun, type WorkspaceEntry } from '@/services/api/agentos'
import type { RunActionCapabilities } from '@/services/api/agentos'
import { ElMessageBox } from 'element-plus'

let wrapper: VueWrapper | undefined
let status = 'planning'
let entries: WorkspaceEntry[] = []
let streams = 0
let details: Record<string, WorkflowRun> = {}
let runList: MissionWorkspaceProjection['runs'] | null = null
let unexpectedReads: string[] = []
let offersByRun: Record<string, Partial<RunActionCapabilities> | null> = {}
const detail = (id = 'a'): WorkflowRun => {
  const run = details[id] || ({ runId: id, missionId: 'm', workflowId: 'workflow', domain: 'general', status, steps: [], review: status === 'waiting_review' ? { stepId: 'node' } : undefined } as any)
  const superseded = run.status === 'superseded' || Boolean(run.lineage?.supersededByRunId)
  return { ...run, runtimeRevision: run.runtimeRevision ?? 1,
    actionCapabilities: offersByRun[id] === null ? null : capabilitiesFixture(id, 'm', run.status, run.runtimeRevision ?? 1, { lineage: run.lineage || {},
      isSuperseded: superseded, canCancel: !superseded && ['pending', 'planning', 'running', 'waiting_review', 'retrying'].includes(run.status),
      canCollaborate: !superseded && ['pending', 'planning', 'running', 'waiting_review', 'retrying'].includes(run.status),
      canReview: !superseded && Boolean(run.review), canRetrySuccessor: !superseded && run.status === 'failed' && run.steps.some(step => step.status === 'failed'),
      retryStepId: run.steps.find(step => step.status === 'failed')?.stepId || null,
      canRerunSuccessor: !superseded && ['completed', 'failed', 'cancelled'].includes(run.status), canDelete: ['completed', 'failed', 'cancelled', 'superseded'].includes(run.status), ...offersByRun[id] }) }
}
const workspace = (id = 'a'): MissionWorkspaceProjection => ({
  mission: { missionId: 'm', userId: 'u', goal: 'Lifecycle', status: 'created', metadata: {}, createdAt: '1', updatedAt: '1', description: '' },
  activeRun: { runId: id, status: detail(id).status, createdAt: '2026-11-01', isActive: true, actionCapabilities: detail(id).actionCapabilities } as any,
  runs: (runList || [{ runId: id, status: detail(id).status, createdAt: '2026-11-01', isActive: true }]).map(run => ({ ...run, actionCapabilities: detail(run.runId).actionCapabilities })) as any,
  entries: [{ entryId: 'overview:mission.md', kind: 'virtual_document', group: 'overview', name: 'mission.md', content: '# Mission', displayOrder: 0 }, ...entries.filter(entry => !entry.runId || entry.runId === id)],
  graphNodes: [], diagnostics: []
})
const finalEntry = (): WorkspaceEntry => ({ entryId: 'final', kind: 'artifact', name: 'delivery.md', group: 'output', displayOrder: 0,
  runId: 'a', artifactId: 'artifact-a', contentRef: 'manifest-a', artifactKey: 'final', artifactType: 'run_deliverable', identityQuality: 'canonical', mediaType: 'text/markdown' })
const settle = async () => { await flushPromises(); await vi.dynamicImportSettled(); await flushPromises() }
const view = () => wrapper!.findComponent(MissionWorkspaceView).vm as any
const open = async (url = '/agentos/missions/m/workspace?runId=a') => {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/agentos/missions/:missionId/workspace', component: MissionWorkspaceView },
    { path: '/elsewhere', component: { template: '<p>elsewhere</p>' } }
  ] })
  await router.push(url); await router.isReady()
  wrapper = mount({ components: { WorkspaceViewHost }, template: '<router-view v-slot="{ Component, route }"><WorkspaceViewHost :view="Component" :view-route="route" /></router-view>' }, {
    global: { plugins: [createPinia(), router], stubs: {
      WorkbenchLayout: { template: '<div><slot name="left"/><slot name="main" :rightPaneVisible="true" :rightAutoHidden="false" :leftAutoHidden="false" :toggleRightPane="() => {}"/><slot name="right"/><slot name="bottom" :collapsed="false" :setCollapsed="() => {}"/><slot name="status-bar" :collapsed="false" :setCollapsed="() => {}"/></div>' },
      AcgTopologyGraph: true, 'el-icon': true
    } }
  })
  await settle(); return router
}
beforeEach(() => {
  vi.useFakeTimers(); localStorage.clear(); sessionStorage.clear(); status = 'planning'; entries = []; streams = 0; details = {}; runList = null
  unexpectedReads = []
  offersByRun = {}
  vi.spyOn(agentosRequest, 'get').mockImplementation(async (path: string) => { unexpectedReads.push(path); throw new Error(`Unmocked fixture GET: ${path}`) })
  vi.spyOn(agentosRequest, 'post').mockRejectedValue(new Error('Unexpected mutation from a presentation transition'))
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  window.matchMedia = vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })) as any
  HTMLElement.prototype.scrollTo = vi.fn()
  vi.spyOn(agentosApi, 'getMissionWorkspace').mockImplementation(async (_id, options) => workspace(options?.runId || 'a'))
  vi.spyOn(agentosApi, 'getWorkflowRun').mockImplementation(async id => detail(id))
  vi.spyOn(agentosApi, 'getWorkflowTrace').mockImplementation(async id => ({ runId: id, events: [] } as any))
  vi.spyOn(agentosApi, 'getRunProvenance').mockImplementation(async id => ({ runId: id, productions: [], consumptions: [], interactions: [] } as any))
  vi.spyOn(agentosApi, 'getExecutionTree').mockImplementation(async id => ({ runId: id, nodes: [], lineage: detail(id).lineage } as any))
  vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [], total: 0 } as any)
  vi.spyOn(agentosApi, 'listWorkflowReviews').mockResolvedValue({ items: [] } as any)
  vi.spyOn(agentosApi, 'listRunContextPacks').mockResolvedValue({ items: [] } as any)
  vi.spyOn(agentosApi, 'listWorkspaceFiles').mockResolvedValue({ workspaceRoot: '/workspace', path: '', entries: [] })
  vi.spyOn(agentosApi, 'getRunRevision').mockResolvedValue({ status: 'CURRENT' } as any)
  vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ manifestId: 'manifest-a', content: '# Final A', mediaType: 'text/markdown' } as any)
  vi.spyOn(agentosApi, 'getCopilot').mockImplementation(async id => ({ runId: id, missionId: 'm', status: detail(id).status, revision: 1, modelAvailable: true, taskPermission: 'task_collaboration', question: null, humanAnswers: [], exchanges: [], decision: null, steps: [] }))
  vi.spyOn(agentosApi, 'streamCopilotMessage').mockImplementation(async (_id, content, operationId) => ({ operationId, user: content, assistant: 'discussion', observedRevision: 1, createdAt: 'now' }))
  vi.stubGlobal('fetch', vi.fn(async (_url, options) => {
    streams++
    return new Response(new ReadableStream({ start(controller) {
      options?.signal?.addEventListener('abort', () => { streams--; controller.error(new DOMException('aborted', 'AbortError')) }, { once: true })
    } }), { headers: { 'Content-Type': 'text/event-stream' } })
  }))
})
afterEach(async () => { wrapper?.unmount(); wrapper = undefined; await settle(); expect(streams).toBe(0); expect(unexpectedReads).toEqual([]); expect(agentosRequest.post).not.toHaveBeenCalled(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('restores Cancel independently for each active Run and preserves the comparison revision', async () => {
  status = 'running'
  details.a = { ...detail(), runtimeRevision: 9 }
  details.b = { ...detail('b'), runtimeRevision: 3 }
  const cancel = vi.spyOn(agentosApi, 'cancelWorkflowRun').mockImplementation(async id => {
    details[id] = { ...detail(id), status: 'cancelled', runtimeRevision: detail(id).runtimeRevision! + 1 }
    return detail(id)
  })
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
  await open()
  expect(view().canCancelActiveRun).toBe(true)
  expect(view().controlReadOnly).toBe(false)
  await wrapper!.get('[aria-label="打开 ACG Copilot"]').trigger('click'); await settle()
  const stop = wrapper!.findAll('.formal-control__actions button').find(button => button.text() === '取消任务')!
  expect(stop).toBeDefined()
  await stop.trigger('click'); await settle()
  expect(cancel).toHaveBeenCalledWith('a', { expectedRuntimeRevision: 9 })
  expect(view().lifecycle.phase).toBe('CANCELLED')
  expect(view().canCancelActiveRun).toBe(false)
  await view().selectRun('b'); await settle()
  expect(view().canCancelActiveRun).toBe(true)
  offersByRun.b = { canCancel: false, canCollaborate: false }
  await view().loadWorkspace('b'); await settle()
  await view().cancelActiveRun()
  expect(cancel).toHaveBeenCalledTimes(1)
})

it('does not turn Cancel permission into Review, tool approval or formal permission', async () => {
  status = 'waiting_review'
  offersByRun.a = { canReview: false, canExecuteFormalAction: false, canResolveToolApproval: false }
  vi.mocked(agentosApi.getCopilot).mockResolvedValue({ runId: 'a', missionId: 'm', status, revision: 1,
    modelAvailable: true, question: null, humanAnswers: [], exchanges: [], decision: null, steps: [],
    review: { subjectId: 'node', subjectType: 'step', reason: 'Review requested', reasonCode: 'REVIEW_REQUIRED',
      canApprove: true, decisionRejected: false, expectedRunUpdatedAt: '2026-11-02T00:00:00Z' } })
  await open()
  expect(view().canCancelActiveRun).toBe(true)
  if (!wrapper!.findComponent({ name: 'AcgCopilotPanel' }).exists()) {
    await wrapper!.get('[aria-label="打开 ACG Copilot"]').trigger('click'); await settle()
  }
  const copilot = wrapper!.findComponent({ name: 'AcgCopilotPanel' })
  const review = vi.spyOn(agentosApi, 'applyWorkflowReview')
  await (copilot.vm as any).submitReview('approved')
  expect(copilot.get('.review-actions button').attributes('disabled')).toBeDefined()
  expect(review).not.toHaveBeenCalled()
  expect(wrapper!.findComponent({ name: 'FormalToolApprovals' }).exists()).toBe(false)
})

it('closes missing capability snapshots and refuses superseded sources without creating a successor', async () => {
  status = 'failed'
  offersByRun.a = null
  await open()
  expect(view().controlReadOnly).toBe(true)
  expect(view().canRerunSelectedRun).toBe(false)
  delete offersByRun.a
  details.a = { ...detail(), lineage: { supersededByRunId: 'b' } }
  await view().loadWorkspace('a'); await settle()
  const retry = vi.spyOn(agentosApi, 'retryWorkflowStepAsync')
  const rerun = vi.spyOn(agentosApi, 'rerunWorkflowAsync')
  await view().rerunSelectedRun()
  expect(view().isHistorical).toBe(true)
  expect(retry).not.toHaveBeenCalled(); expect(rerun).not.toHaveBeenCalled()
})

it('allows offered superseded soft deletion while keeping independent branch controls', async () => {
  status = 'superseded'
  details.a = { ...detail('a'), lineage: { supersededByRunId: 'b' } }
  details.b = { ...detail('b'), status: 'running', lineage: { sourceRunId: 'a' } } as any
  runList = [{ runId: 'a', status: 'superseded', createdAt: '2026-11-01', isActive: true },
    { runId: 'b', status: 'running', createdAt: '2026-11-02', isActive: false }]
  const removed = vi.spyOn(agentosApi, 'deleteWorkflowRun').mockResolvedValue({} as any)
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
  await open('/agentos/missions/m/workspace?runId=b')
  expect(view().runPickerItems.find((row: any) => row.runId === 'a').canDelete).toBe(true)
  await view().deletePickerRun('a'); await settle()
  expect(removed).toHaveBeenCalledWith('a')
  expect(view().selectedRunId).toBe('b')
  expect(view().canCancelActiveRun).toBe(true)
  offersByRun.a = { canDelete: false }
  await view().loadWorkspace('b'); await settle()
  await view().deletePickerRun('a')
  expect(removed).toHaveBeenCalledTimes(1)
})

it.each(['revision', 'target'])('does not silently replace a stale retry %s with another version or a full rerun', async mismatch => {
  status = 'failed'
  details.a = { ...detail(), runtimeRevision: 4, steps: [{ stepId: 'node', status: 'failed' }] } as any
  if (mismatch === 'target') offersByRun.a = { retryStepId: 'other-node' }
  await open()
  if (mismatch === 'revision') vi.mocked(agentosApi.getWorkflowRun).mockResolvedValueOnce({ ...detail(), runtimeRevision: 5 })
  const retry = vi.spyOn(agentosApi, 'retryWorkflowStepAsync')
  const rerun = vi.spyOn(agentosApi, 'rerunWorkflowAsync')
  await view().rerunSelectedRun(); await settle()
  expect(retry).not.toHaveBeenCalled(); expect(rerun).not.toHaveBeenCalled()
  expect(view().selectedRunId).toBe('a')
  expect(Array.from({ length: sessionStorage.length }, (_, index) => sessionStorage.key(index))
    .some(key => key?.startsWith('workbench.recovery.v1:'))).toBe(false)
})
it.each(['failed', 'completed'])('real Registry and EditorGroup follow planning, execution, review and %s once', async terminal => {
  await open()
  expect(wrapper!.findComponent(EditorGroup).exists()).toBe(true)
  expect(view().activeEditorId).toBe('run:a:progress'); expect(view().lifecycle.phase).toBe('PLANNING')
  for (const next of ['running', 'waiting_review', terminal]) {
    status = next; await view().loadWorkspace(); await vi.advanceTimersByTimeAsync(2100); await settle()
    expect(view().lifecycle.rawStatus).toBe(next)
  }
  if (terminal === 'failed') {
    expect(view().activeEditorId).toBe('run:a:progress')
    expect(view().lifecycle.failure.objectId).toBe('a')
    return
  }
  expect(wrapper!.text()).toContain('Completed · Final deliverable missing')
  expect(view().activeEditorId).toBe('run:a:progress')
  entries = [finalEntry()]; await view().loadWorkspace(); await settle()
  expect(view().activeEditorId).toBe('final'); expect(wrapper!.text()).toContain('Final A')
  const handled = view().editorIntent.handled
  await view().loadWorkspace(); await settle()
  expect(view().editorIntent.handled).toBe(handled); expect(view().openEditors.filter((id: string) => id === 'final')).toHaveLength(1)
})
it('manual reading survives state changes and KeepAlive; explicit Follow hands off to final delivery', async () => {
  const router = await open()
  view().openEntry(workspace().entries[0]); await settle()
  expect(view().editorIntent.mode).toBe('user')
  status = 'completed'; entries = [finalEntry()]
  await view().loadWorkspace(); await vi.advanceTimersByTimeAsync(2100); await settle()
  expect(view().activeEditorId).toBe('overview:mission.md')
  const uid = view().$.uid
  await router.push('/elsewhere'); await settle(); await router.back(); await settle()
  expect(view().$.uid).toBe(uid); expect(view().activeEditorId).toBe('overview:mission.md')
  await wrapper!.get('.workspace-lifecycle button').trigger('click'); await settle()
  expect(view().activeEditorId).toBe('final')
})

const defer = <T,>() => {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((ok, fail) => { resolve = ok; reject = fail })
  return { promise, resolve, reject }
}
it.each([['completed', 'failed'], ['failed', 'completed']])('keeps selected old %s distinct from latest %s without inventing current authority', async (old, next) => {
  status = old
  details.a = { ...detail('a'), lineage: { supersededByRunId: 'b' } }
  details.b = { ...detail('b'), status: next, lineage: { sourceRunId: 'a', supersedesRunId: 'a' } } as any
  runList = [{ runId: 'b', status: next, createdAt: '2026-11-02', isActive: false }, { runId: 'a', status: old, createdAt: '2026-11-01', isActive: true }] as any
  const router = await open()
  expect(router.currentRoute.value.query.runId).toBe('a')
  expect(view().selectedRunId).toBe('a'); expect(view().lifecycle.latestRunId).toBe('b')
  expect(view().isHistorical).toBe(true); expect(view().controlReadOnly).toBe(true); expect(view()).not.toHaveProperty('currentRunId')
  const cancel = vi.spyOn(agentosApi, 'cancelWorkflowRun')
  await view().cancelActiveRun(); expect(cancel).not.toHaveBeenCalled()
  await view().selectRun('b'); await settle()
  expect(view().lifecycle.isHistorical).toBe(false); expect(view().lifecycle).not.toHaveProperty('isCurrent')
  expect(view().runtimeObservation.run.runId).toBe('b')
})
it('historical Copilot discusses evidence with read_only permission and cannot issue a control', async () => {
  status = 'failed'; details.a = { ...detail(), lineage: { supersededByRunId: 'b' } }
  await open()
  await wrapper!.get('[aria-label="打开 ACG Copilot"]').trigger('click'); await settle()
  const preview = vi.spyOn(agentosApi, 'previewCopilotAction')
  const apply = vi.spyOn(agentosApi, 'applyCopilotAction')
  const formal = vi.spyOn(agentosApi, 'submitFormalControl')
  const copilot = wrapper!.findComponent({ name: 'AcgCopilotPanel' })
  expect(copilot.props('readonly')).toBe(true)
  await copilot.get('textarea').setValue('Explain historical failure')
  await copilot.get('form').trigger('submit'); await settle()
  expect(agentosApi.streamCopilotMessage).toHaveBeenCalledWith('a', 'Explain historical failure', expect.any(String), expect.any(Function), expect.anything(), expect.objectContaining({ permission: 'read_only' }))
  await (copilot.vm as any).prepareOperation('recover')
  await (copilot.vm as any).confirmAction('proposal', {}, 'a')
  expect(preview).not.toHaveBeenCalled(); expect(apply).not.toHaveBeenCalled(); expect(formal).not.toHaveBeenCalled()
})
it.each(['retry', 'rerun'])('persists %s operation after a lost response, deduplicates submission, and creates only a successor', async kind => {
  status = kind === 'retry' ? 'failed' : 'completed'
  details.a = { ...detail(), runtimeRevision: 4, lineage: { sourceRunId: 'predecessor' }, steps: [{ stepId: 'node', status: 'failed' }] } as any
  const original = JSON.stringify(details.a)
  const ledger = new Map<string, WorkflowRun>()
  const response = defer<WorkflowRun>()
  const api = kind === 'retry' ? vi.spyOn(agentosApi, 'retryWorkflowStepAsync') : vi.spyOn(agentosApi, 'rerunWorkflowAsync')
  vi.spyOn(agentosApi, 'getWorkflowHistoryConfig').mockResolvedValue({ runId: 'a', input: { goal: 'immutable source' }, reviewMode: 'auto' })
  api.mockImplementationOnce(((...args: any[]) => {
    const payload = args[kind === 'retry' ? 2 : 1]
    details.b = { ...detail('b'), status: 'pending', lineage: { sourceRunId: 'a' } } as any
    ledger.set(payload.clientRequestId, details.b)
    return response.promise
  }) as any).mockImplementation(((...args: any[]) => Promise.resolve(ledger.get(args[kind === 'retry' ? 2 : 1].clientRequestId)!)) as any)
  await open()
  const pending = view().rerunSelectedRun(); await settle()
  await view().rerunSelectedRun(); expect(api).toHaveBeenCalledTimes(1)
  response.reject(new Error('response lost')); await pending; await settle()
  const first = JSON.stringify(api.mock.calls[0][kind === 'retry' ? 2 : 1])
  if (kind === 'retry') expect(api.mock.calls[0][2]).toMatchObject({ mode: 'successor_run', expectedRuntimeRevision: 4 })
  wrapper!.unmount(); wrapper = undefined; await settle()
  const router = await open()
  await view().rerunSelectedRun(); await settle()
  expect(JSON.stringify(api.mock.calls[1][kind === 'retry' ? 2 : 1])).toBe(first)
  expect(api).toHaveBeenCalledTimes(2); expect(ledger.size).toBe(1)
  expect(router.currentRoute.value.query.runId).toBe('b')
  expect(view().selectedRunId).toBe('b'); expect(view().runtimeObservation.run.runId).toBe('b')
  expect(JSON.stringify(details.a)).toBe(original)
})
it('late Projection and Observation cannot replace the URL, graph or evidence of a newer selection; back/forward stays coherent', async () => {
  status = 'running'
  const router = await open()
  const lateProjection = defer<MissionWorkspaceProjection>()
  const lateDetail = defer<WorkflowRun>()
  vi.mocked(agentosApi.getMissionWorkspace).mockImplementationOnce(() => lateProjection.promise)
  const refreshing = view().loadWorkspace('a'); await flushPromises()
  vi.mocked(agentosApi.getWorkflowRun).mockImplementationOnce(() => lateDetail.promise)
  await vi.advanceTimersByTimeAsync(2100); await flushPromises()
  await view().selectRun('b'); await settle()
  lateProjection.resolve(workspace('a')); lateDetail.resolve(detail('a')); await refreshing; await settle()
  expect(router.currentRoute.value.query.runId).toBe('b'); expect(view().projection.activeRun.runId).toBe('b')
  expect(view().runtimeObservation.runId).toBe('b'); expect(view().runtimeStore.runId).toBe('b')
  router.back(); await settle(); expect(view().selectedRunId).toBe('a'); expect(view().runtimeObservation.runId).toBe('a')
  router.forward(); await settle(); expect(view().selectedRunId).toBe('b'); expect(view().runtimeObservation.runId).toBe('b')
})
it.each([403, 404, 0])('a new Run request failing with %s stays explicit and never renders the old Run as the new one', async code => {
  const router = await open()
  const reject = () => Promise.reject({ response: code ? { status: code } : undefined })
  vi.mocked(agentosApi.getMissionWorkspace).mockImplementation(async (_mission, options) => options?.runId === 'missing' ? reject() : workspace(options?.runId))
  vi.mocked(agentosApi.getWorkflowRun).mockImplementation(async id => id === 'missing' ? reject() : detail(id))
  const selecting = view().selectRun('missing'); await settle(); await selecting
  expect(router.currentRoute.value.query.runId).toBe('missing'); expect(view().selectedRunId).toBe('missing')
  expect(view().projection).toBeNull(); expect(view().runtimeObservation).toBeNull(); expect(view().runtimeStore).toBeNull()
  expect(view().loadError).not.toBe(''); expect(wrapper!.findComponent(EditorGroup).exists()).toBe(false)
})
it('external successors update the list while preserving selected Run and its original Artifact and Provenance', async () => {
  status = 'completed'; entries = [finalEntry()]
  const router = await open()
  const originalArtifact = JSON.stringify(view().projection.entries.find((entry: WorkspaceEntry) => entry.entryId === 'final'))
  const originalProvenance = JSON.stringify(view().runtimeObservation.provenance)
  runList = [{ runId: 'b', status: 'failed', createdAt: '2026-11-02', isActive: false }, { runId: 'a', status: 'completed', createdAt: '2026-11-01', isActive: true }]
  await view().loadWorkspace(); await settle()
  expect(view().selectedRunId).toBe('a'); expect(router.currentRoute.value.query.runId).toBe('a')
  expect(view().lifecycle.latestRunId).toBe('b'); expect(view().lifecycle).not.toHaveProperty('currentRunId')
  expect(JSON.stringify(view().projection.entries.find((entry: WorkspaceEntry) => entry.entryId === 'final'))).toBe(originalArtifact)
  expect(JSON.stringify(view().runtimeObservation.provenance)).toBe(originalProvenance)
})

it('Run navigation through the real Explorer keeps Graph, Editor, Observation and URL on B after a late A projection', async () => {
  status = 'running'
  runList = [{ runId: 'a', status: 'running', createdAt: '2026-11-01', isActive: true }, { runId: 'b', status: 'running', createdAt: '2026-11-02', isActive: false }]
  const graphWorkspace = (id: string) => ({ ...workspace(id), activeGraph: { graphId: `graph-${id}`, nodes: [], edges: [] },
    entries: [...workspace(id).entries, { entryId: 'graph', kind: 'graph', runId: id, name: 'graph.acg', group: 'overview', displayOrder: 0 }] } as MissionWorkspaceProjection)
  vi.mocked(agentosApi.getMissionWorkspace).mockImplementation(async (_id, options) => graphWorkspace(options?.runId || 'a'))
  const router = await open()
  const delayed = defer<MissionWorkspaceProjection>()
  vi.mocked(agentosApi.getMissionWorkspace).mockImplementationOnce(() => delayed.promise)
  const old = view().loadWorkspace(); await settle()
  await wrapper!.findAll('.workspace-tree__entry').find(entry => entry.text() === 'b')!.trigger('click'); await settle()
  await wrapper!.findAll('.workspace-tree__entry').find(entry => entry.text().includes('graph.acg'))!.trigger('click'); await settle()
  delayed.resolve(graphWorkspace('a')); await old; await settle()
  expect(router.currentRoute.value.query.runId).toBe('b')
  expect(view().activeEditorId).toBe('graph')
  expect(view().projection.activeGraph.graphId).toBe('graph-b')
  expect(wrapper!.findComponent(GraphEditor).props('graph')?.graphId).toBe('graph-b')
  expect(view().runtimeObservation.runId).toBe('b'); expect(view().runtimeStore.runId).toBe('b')
  expect(streams).toBe(1)
})
it('a failed successor is a valid source for another successor without changing the older Run', async () => {
  status = 'failed'
  details.a = { ...detail('a'), lineage: { supersededByRunId: 'b' } }
  details.b = { ...detail('b'), runtimeRevision: 7, lineage: { sourceRunId: 'a' }, steps: [{ stepId: 'failed-node', status: 'failed' }] } as any
  details.c = { ...detail('c'), status: 'pending', lineage: { sourceRunId: 'b' } } as any
  const original = JSON.stringify(details.a)
  const retry = vi.spyOn(agentosApi, 'retryWorkflowStepAsync').mockResolvedValue(details.c)
  const router = await open('/agentos/missions/m/workspace?runId=b')
  await view().rerunSelectedRun(); await settle()
  expect(retry).toHaveBeenCalledWith('b', 'failed-node', expect.objectContaining({ mode: 'successor_run', expectedRuntimeRevision: 7 }))
  expect(router.currentRoute.value.query.runId).toBe('c'); expect(JSON.stringify(details.a)).toBe(original)
})
it('failure locates an actual failed Task and review opens the existing review surface without approving', async () => {
  entries = [{ entryId: 'task', kind: 'task', name: 'Task', group: 'steps', runId: 'a', displayOrder: 0, acgNodeId: 'node', semanticTaskKey: 'task' }]
  await open()
  status = 'waiting_review'; await view().loadWorkspace(); await vi.advanceTimersByTimeAsync(2100); await settle()
  expect(view().activeEditorId).toBe('task'); expect(view().activeAuxiliaryId).toBe('acg-copilot.sidebar')
  const approve = vi.spyOn(agentosApi, 'applyWorkflowReview')
  status = 'failed'; details.a = { ...detail(), steps: [{ stepId: 'node', status: 'failed' }], lifecycleMessage: 'Task failed for a recorded reason' } as any
  await view().loadWorkspace(); await vi.advanceTimersByTimeAsync(2100); await settle()
  expect(view().activeEditorId).toBe('task'); expect(view().lifecycle.failure.objectId).toBe('node')
  expect(approve).not.toHaveBeenCalled()
})
it('a background successor request from A cannot block or finish B own recovery UI', async () => {
  status = 'failed'
  details.a = { ...detail('a'), runtimeRevision: 1, steps: [{ stepId: 'node', status: 'failed' }] } as any
  details.b = { ...detail('b'), runtimeRevision: 2, steps: [{ stepId: 'node', status: 'failed' }] } as any
  details.c = { ...detail('c'), status: 'pending', lineage: { sourceRunId: 'b' } } as any
  const a = defer<WorkflowRun>(), b = defer<WorkflowRun>()
  const retry = vi.spyOn(agentosApi, 'retryWorkflowStepAsync').mockImplementation(id => id === 'a' ? a.promise : b.promise)
  const router = await open()
  const first = view().rerunSelectedRun(); await settle()
  await view().selectRun('b'); await settle()
  const second = view().rerunSelectedRun(); await settle()
  try {
    expect(retry).toHaveBeenCalledTimes(2)
    a.resolve({ ...detail('a-next'), status: 'pending', lineage: { sourceRunId: 'a' } } as any)
    await first; await settle()
    expect(router.currentRoute.value.query.runId).toBe('b'); expect(view().rerunPending).toBe(true)
  } finally {
    a.resolve({ ...detail('a-next'), status: 'pending', lineage: { sourceRunId: 'a' } } as any)
    b.resolve(details.c); await Promise.all([first, second]); await settle()
  }
  expect(router.currentRoute.value.query.runId).toBe('c'); expect(view().rerunPending).toBe(false)
})
it('a planning failure without Graph or failed nodes can create a fresh successor from its original input', async () => {
  status = 'failed'
  details.a = { ...detail('a'), lifecyclePhase: 'planning', lifecycleMessage: 'Planner unavailable', steps: [] } as any
  details.b = { ...detail('b'), status: 'pending', lineage: { sourceRunId: 'a' } } as any
  const original = JSON.stringify(details.a)
  vi.spyOn(agentosApi, 'getWorkflowHistoryConfig').mockResolvedValue({ runId: 'a', input: { goal: 'original planning goal' } })
  const rerun = vi.spyOn(agentosApi, 'rerunWorkflowAsync').mockResolvedValue(details.b)
  const retry = vi.spyOn(agentosApi, 'retryWorkflowStepAsync')
  const router = await open()
  expect(view().lifecycle.phase).toBe('FAILED'); expect(view().activeEditorId).toBe('run:a:progress')
  await view().rerunSelectedRun(); await settle()
  expect(rerun).toHaveBeenCalledWith('m', expect.objectContaining({ sourceRunId: 'a', input: { goal: 'original planning goal' }, clientRequestId: expect.any(String) }))
  expect(retry).not.toHaveBeenCalled()
  expect(router.currentRoute.value.query.runId).toBe('b'); expect(JSON.stringify(details.a)).toBe(original)
})
