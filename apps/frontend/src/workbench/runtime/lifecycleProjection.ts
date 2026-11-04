import type { MissionWorkspaceProjection, WorkflowRun, WorkspaceEntry, RunActionCapabilities } from '@/services/api/agentos'
import { isRunDeliverableEntry } from './deliverableIdentity'
import { readRunCapabilities, runCapabilities, runCapabilityActions } from './runCapabilities'

export type { LifecyclePhase } from '@/features/workspace/runLifecycle'
import { mapRunPhase, type LifecyclePhase } from '@/features/workspace/runLifecycle'
export interface LifecycleProjection {
  runId: string | null
  rawStatus: string | null
  normalizedStatus: string
  phase: LifecyclePhase
  reason: string
  isHistorical: boolean
  latestRunId: string | null
  successorRunId: string | null
  isReadOnly: boolean
  capabilities: RunActionCapabilities | null
  recommendedEditor: 'mission' | 'progress' | 'graph' | 'task' | 'artifact'
  recommendedEntryId: string | null
  recommendedInspector: 'mission' | 'runtime' | 'review' | 'failure' | 'delivery' | 'lineage' | 'formal'
  availableActions: readonly string[]
  unavailableReasons: readonly string[]
  evidenceReferences: readonly string[]
  notObserved: readonly string[]
  deliverable: WorkspaceEntry | null
  deliveryStatus: 'READY' | 'MISSING' | 'NOT_COMPLETE'
  failure: { layer: string; objectId: string; reason: string; checkpoint: 'NOT_OBSERVED'; sideEffects: 'NOT_OBSERVED' } | null
}

/** Presentation only. Workspace activeRun/isActive are selection markers, never authorization. */
export function projectLifecycle(input: {
  workspace: MissionWorkspaceProjection | null
  selectedRunId: string | null
  run?: WorkflowRun | null
}): LifecycleProjection {
  const { workspace, selectedRunId } = input
  const detail = input.run?.runId === selectedRunId && input.run.missionId === workspace?.mission.missionId ? input.run : null
  const summary = workspace?.activeRun?.runId === selectedRunId ? workspace.activeRun
    : workspace?.runs.find(item => item.runId === selectedRunId) || null
  const offers = [runCapabilities(detail), readRunCapabilities(summary?.actionCapabilities,
    workspace?.mission.missionId || '', selectedRunId)].filter((value): value is RunActionCapabilities => Boolean(value))
  offers.sort((a, b) => b.runtimeRevision - a.runtimeRevision)
  const signature = (value: RunActionCapabilities) => JSON.stringify([value.status, value.isSuperseded,
    value.lineage.supersededByRunId, value.formalActions, ...runCapabilityActions.map(action => value[action])])
  const conflict = offers.some(value => value.runtimeRevision === offers[0].runtimeRevision && signature(value) !== signature(offers[0]))
  const capabilities = conflict ? null : offers[0] || null
  const run = !conflict && detail && (!capabilities || detail.runtimeRevision === capabilities.runtimeRevision) ? detail : null
  const rawStatus = capabilities?.status || run?.status || summary?.status || null
  const status = rawStatus?.toLowerCase() || 'unknown'
  const control = run?.formalControl
  const evidence = [run ? `run:${selectedRunId}:status` : summary ? `workspace:${selectedRunId}:status` : 'status:NOT_OBSERVED']
  let { phase, reason } = mapRunPhase(rawStatus, run, selectedRunId, Boolean(workspace))
  if (control) evidence.push(`run:${selectedRunId}:formalControl:${control.status}`)
  if (run?.lifecyclePhase) evidence.push(`run:${selectedRunId}:lifecyclePhase:${run.lifecyclePhase}`)
  if (run?.failureCode || run?.error?.code) evidence.push(`run:${selectedRunId}:failure:${run.failureCode || run.error?.code}`)
  if (run?.review) evidence.push(`run:${selectedRunId}:review:${run.review.subjectId || run.review.stepId || 'unknown'}`)
  if (conflict) {
    phase = 'UNKNOWN'; reason = 'Run capability snapshots disagree at the same runtimeRevision; controls disabled'
    evidence.push('actionCapabilities:SNAPSHOT_CONFLICT')
  }
  const successorRunId = capabilities?.lineage.supersededByRunId || detail?.lineage?.supersededByRunId || null
  const historical = capabilities?.isSuperseded === true || status === 'superseded' || Boolean(successorRunId)
  const unavailableReasons = historical ? ['Historical Run is immutable'] : !capabilities
    ? ['Run Action Capabilities NOT_OBSERVED; controls disabled'] : capabilities.unavailableReasons.map(reason => `${reason.action}: ${reason.code}`)
  const dates = (workspace?.runs || []).map(item => ({ id: item.runId, time: Date.parse(item.createdAt) }))
  const maximum = Math.max(...dates.map(item => item.time))
  const latest = dates.filter(item => Number.isFinite(item.time) && item.time === maximum)
  const entries = (workspace?.entries || []).filter(entry => !entry.runId || entry.runId === selectedRunId)
  const deliverable = phase === 'COMPLETED' ? entries.find(entry => entry.kind === 'artifact'
    && entry.runId === selectedRunId && entry.identityQuality === 'canonical' && isRunDeliverableEntry(entry)
    && Boolean(entry.artifactId?.trim() && entry.contentRef?.trim())) || null : null
  const failedStep = run?.steps?.find(step => step.status === 'failed')
  const failureTask = failedStep ? entries.find(entry => entry.kind === 'task'
    && (entry.acgNodeId === failedStep.stepId || entry.semanticTaskKey === failedStep.stepId)) : undefined
  let recommendedEditor: LifecycleProjection['recommendedEditor'] = phase === 'CREATED' ? 'mission' : 'progress'
  let recommendedEntryId: string | null = null
  if (deliverable) { recommendedEditor = 'artifact'; recommendedEntryId = deliverable.entryId; evidence.push(`artifact:${deliverable.artifactId}:run_deliverable`) }
  else if (phase === 'FAILED' && failureTask) { recommendedEditor = 'task'; recommendedEntryId = failureTask.entryId }
  else if (phase === 'WAITING_REVIEW' && run?.review?.stepId) {
    const task = entries.find(entry => entry.kind === 'task' && entry.acgNodeId === run.review?.stepId)
    if (task) { recommendedEditor = 'task'; recommendedEntryId = task.entryId }
  } else if (['AWAITING_CONFIRMATION', 'ACTIVATED_PAUSED', 'READY_TO_DISPATCH'].includes(phase)) {
    const graph = entries.find(entry => entry.kind === 'graph')
    if (graph) { recommendedEditor = 'graph'; recommendedEntryId = graph.entryId }
  }
  const inspector: LifecycleProjection['recommendedInspector'] = phase === 'CREATED' ? 'mission'
    : phase === 'FAILED' ? 'failure' : phase === 'COMPLETED' ? 'delivery' : historical ? 'lineage'
    : phase === 'WAITING_REVIEW' ? 'review' : ['ACTIVATED_PAUSED', 'READY_TO_DISPATCH', 'AWAITING_CONFIRMATION'].includes(phase) ? 'formal' : 'runtime'
  return {
    runId: selectedRunId, rawStatus, normalizedStatus: status === 'succeeded' ? 'completed' : status,
    phase, reason, isHistorical: historical,
    latestRunId: latest.length === 1 ? latest[0].id : null, successorRunId, capabilities,
    isReadOnly: historical || !capabilities || !['canCancel', 'canReview', 'canExecuteFormalAction', 'canAnswerPlanner',
      'canCollaborate', 'canResolveToolApproval', 'canDecideRevision', 'canApplyRevision'].some(key => capabilities[key as keyof RunActionCapabilities] === true),
    recommendedEditor, recommendedEntryId, recommendedInspector: inspector,
    availableActions: selectedRunId ? ['inspect', 'discuss', ...(capabilities?.canRetrySuccessor || capabilities?.canRerunSuccessor ? ['create_successor'] : [])] : ['inspect'],
    unavailableReasons, evidenceReferences: evidence,
    notObserved: [...(!run && selectedRunId ? ['runDetail'] : []), ...(!capabilities ? ['actionCapabilities'] : []), ...(!control ? ['formalControl'] : []), 'checkpointRecoveryAuthorization'],
    deliverable, deliveryStatus: phase !== 'COMPLETED' ? 'NOT_COMPLETE' : deliverable ? 'READY' : 'MISSING',
    failure: phase === 'FAILED' ? { layer: failedStep ? 'Task' : run?.lifecyclePhase === 'planning' ? 'Planner' : 'Run (layer NOT_OBSERVED)',
      objectId: failedStep?.stepId || selectedRunId || 'unknown', reason, checkpoint: 'NOT_OBSERVED', sideEffects: 'NOT_OBSERVED' } : null
  }
}
