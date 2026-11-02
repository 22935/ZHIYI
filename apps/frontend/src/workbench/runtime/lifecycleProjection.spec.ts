import { describe, expect, it } from 'vitest'
import { projectLifecycle } from './lifecycleProjection'
import type { MissionWorkspaceProjection, WorkflowRun } from '@/services/api/agentos'

const workspace = (status = 'pending'): MissionWorkspaceProjection => ({ mission: { missionId: 'm' } as any,
  activeRun: { runId: 'a', status, isActive: true } as any,
  runs: [{ runId: 'b', status: 'failed', createdAt: '2026-11-02', isActive: false }, { runId: 'a', status, createdAt: '2026-11-01', isActive: true }] as any,
  entries: [], graphNodes: [], diagnostics: [] })
const run = (status: string, formalControl?: object): WorkflowRun => ({ runId: 'a', missionId: 'm', status, steps: [], formalControl } as any)
const project = (status: string, formalControl?: object) => projectLifecycle({ workspace: workspace(status), selectedRunId: 'a', run: run(status, formalControl) })
describe('lifecycle presentation facts, never authorization', () => {
  it.each([['pending', 'QUEUED'], ['queued', 'QUEUED'], ['planning', 'PLANNING'], ['running', 'RUNNING'],
    ['waiting_review', 'WAITING_REVIEW'], ['retrying', 'RECOVERING'], ['failed', 'FAILED'], ['completed', 'COMPLETED'],
    ['succeeded', 'COMPLETED'], ['cancelled', 'CANCELLED'], ['superseded', 'SUPERSEDED'], ['paused', 'UNKNOWN'], ['skipped_by_condition', 'UNKNOWN'], ['alien', 'UNKNOWN']])('%s -> %s', (raw, phase) => {
    const result = project(raw); expect(result.phase).toBe(phase); expect(result.rawStatus).toBe(raw)
    expect(result.evidenceReferences[0]).toContain('run:a:status'); expect(result.isReadOnly).toBe(true)
  })
  it.each([['PLANNING_ACCEPTED', 'AWAITING_CONFIRMATION'], ['MATERIALIZED_INACTIVE', 'AWAITING_CONFIRMATION'],
    ['ACTIVATED_PAUSED', 'ACTIVATED_PAUSED'], ['ACTIVATED', 'READY_TO_DISPATCH']])('formal %s -> %s', (status, phase) => {
    expect(project('pending', { status, permitStatus: 'ISSUED', dispatchEligible: true, dispatchEnabled: true }).phase).toBe(phase)
  })
  it('separates persisted dispatch acceptance from execution and does not infer review from paused', () => {
    expect(project('pending', { status: 'ACTIVATED', dispatch: { runId: 'a', status: 'ACCEPTED' } }).phase).toBe('DISPATCHED')
    expect(project('running', { status: 'ACTIVATED_PAUSED' }).phase).toBe('RUNNING')
    expect(project('waiting_review', { status: 'ACTIVATED_PAUSED' }).phase).toBe('WAITING_REVIEW')
  })
  it('keeps failure without Graph and unknown formal failure evidence', () => {
    expect(project('failed').recommendedEditor).toBe('progress')
    const failed = run('pending', { status: 'CONTROL_FAILED' }); failed.failureCode = 'FORMAL_FAILURE'
    expect(projectLifecycle({ workspace: workspace(), selectedRunId: 'a', run: failed })).toMatchObject({ phase: 'FAILED', reason: 'FORMAL_FAILURE' })
  })
  it('does not promote supporting, foreign, legacy or unreferenced artifacts to delivery', () => {
    const w = workspace('succeeded')
    const artifact = { entryId: 'final', kind: 'artifact', runId: 'a', artifactKey: 'final', artifactType: 'run_deliverable', identityQuality: 'canonical', artifactId: 'id', contentRef: 'ref' } as any
    for (const patch of [{ artifactType: 'supporting' }, { runId: 'b' }, { identityQuality: 'legacy' }, { contentRef: '' }, { artifactId: '' }]) {
      w.entries = [{ ...artifact, ...patch }]
      expect(projectLifecycle({ workspace: w, selectedRunId: 'a' }).deliveryStatus).toBe('MISSING')
    }
    w.entries = [artifact]
    expect(projectLifecycle({ workspace: w, selectedRunId: 'a' }).recommendedEntryId).toBe('final')
  })
  it('does not turn selected/isActive/latest timestamps into current authority', () => {
    expect(project('succeeded')).toMatchObject({ latestRunId: 'b', isReadOnly: true })
    expect(project('succeeded')).not.toHaveProperty('currentRunId')
    const detail = run('failed'); detail.lineage = { supersededByRunId: 'b' }
    expect(projectLifecycle({ workspace: workspace('failed'), selectedRunId: 'a', run: detail })).toMatchObject({ isHistorical: true, successorRunId: 'b' })
  })
  it('ignores foreign Run details and leaves unobserved data explicit', () => {
    const detail = run('completed'); detail.runId = 'b'
    expect(projectLifecycle({ workspace: workspace('planning'), selectedRunId: 'a', run: detail })).toMatchObject({ phase: 'PLANNING', notObserved: expect.arrayContaining(['runDetail', 'actionCapabilities']) })
    expect(projectLifecycle({ workspace: workspace(), selectedRunId: null }).phase).toBe('CREATED')
    expect(projectLifecycle({ workspace: null, selectedRunId: 'a' }).phase).toBe('UNKNOWN')
  })
  it('uses persisted lifecycle hints without treating unknown formal state as queued', () => {
    const detail = run('pending'); detail.lifecyclePhase = 'graph_building'
    expect(projectLifecycle({ workspace: workspace(), selectedRunId: 'a', run: detail }).phase).toBe('PLANNING')
    expect(project('pending', { status: 'UNRECOGNIZED_CONTROL' }).phase).toBe('UNKNOWN')
    expect(project('pending', { status: 'AWAITING_PLANNING' }).phase).toBe('QUEUED')
  })
})
