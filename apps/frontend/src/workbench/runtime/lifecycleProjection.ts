import type { MissionWorkspaceProjection, WorkflowRun, WorkspaceEntry } from '@/services/api/agentos'
import { isRunDeliverableEntry } from './deliverableIdentity'

export type LifecyclePhase = 'CREATED' | 'QUEUED' | 'PLANNING' | 'AWAITING_CONFIRMATION'
  | 'ACTIVATED_PAUSED' | 'READY_TO_DISPATCH' | 'DISPATCHED' | 'RUNNING' | 'WAITING_REVIEW'
  | 'RECOVERING' | 'FAILED' | 'COMPLETED' | 'CANCELLED' | 'SUPERSEDED' | 'UNKNOWN'
export interface LifecycleProjection {
  runId: string | null
  rawStatus: string | null
  normalizedStatus: string
  phase: LifecyclePhase
  reason: string
  isHistorical: boolean
  isCurrent: boolean | null
  currentRunId: string | null
  latestRunId: string | null
  successorRunId: string | null
  isReadOnly: boolean
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
  const run = input.run?.runId === selectedRunId && input.run.missionId === workspace?.mission.missionId ? input.run : null
  const summary = workspace?.activeRun?.runId === selectedRunId ? workspace.activeRun
    : workspace?.runs.find(item => item.runId === selectedRunId) || null
  const rawStatus = run?.status || summary?.status || null
  const status = rawStatus?.toLowerCase() || 'unknown'
  const control = run?.formalControl
  const evidence = [run ? `run:${selectedRunId}:status` : summary ? `workspace:${selectedRunId}:status` : 'status:NOT_OBSERVED']
  let phase: LifecyclePhase = 'UNKNOWN'
  let reason = rawStatus ? `Unrecognized status: ${rawStatus}` : 'Run status NOT_OBSERVED'
  if (['completed', 'succeeded'].includes(status)) { phase = 'COMPLETED'; reason = 'Run reached a successful terminal state' }
  else if (status === 'superseded') { phase = 'SUPERSEDED'; reason = 'Run was superseded; original evidence is read-only' }
  else if (status === 'cancelled') { phase = 'CANCELLED'; reason = 'Run was cancelled' }
  else if (status === 'failed' || run?.failureCode || run?.error?.code) { phase = 'FAILED'; reason = run?.lifecycleMessage || run?.failureCode || run?.error?.code || 'Run failed' }
  else if (status === 'waiting_review') { phase = 'WAITING_REVIEW'; reason = run?.review?.reasonCode || 'An explicit review decision is required' }
  else if (status === 'retrying' || (status === 'running' && run?.lifecyclePhase === 'recovery')) { phase = 'RECOVERING'; reason = 'Runtime reports recovery in progress' }
  else if (status === 'running') { phase = 'RUNNING'; reason = 'Runtime reports execution in progress' }
  else if (['pending', 'planning'].includes(status) && control?.dispatch?.runId === selectedRunId) {
    phase = 'DISPATCHED'; reason = `Dispatch ${control.dispatch.status}; acceptance is not completion`
  } else if (['pending', 'planning'].includes(status) && control?.status === 'ACTIVATED'
    && control.permitStatus === 'ISSUED' && control.dispatchEnabled && control.dispatchEligible) {
    phase = 'READY_TO_DISPATCH'; reason = 'Formal permit issued; dispatch remains an explicit user action'
  } else if (['pending', 'planning'].includes(status) && control?.status === 'ACTIVATED_PAUSED') {
    phase = 'ACTIVATED_PAUSED'; reason = 'Graph activated; execution remains paused'
  } else if (['pending', 'planning'].includes(status) && control
    && ['PLANNING_ACCEPTED', 'MATERIALIZED_INACTIVE', 'ACTIVATION_PREPARED', 'ACTIVATED'].includes(control.status)) {
    phase = 'AWAITING_CONFIRMATION'; reason = `Formal control: ${control.status}`
  } else if (['pending', 'planning'].includes(status) && control && !['AWAITING_PLANNING'].includes(control.status)) {
    phase = 'UNKNOWN'; reason = `Unrecognized formal state: ${control.status}`
  } else if (status === 'planning' || (status === 'pending' && ['understanding', 'planning', 'graph_building'].includes(run?.lifecyclePhase || ''))) { phase = 'PLANNING'; reason = run?.lifecycleMessage || 'Runtime reports planning' }
  else if (status === 'pending' || status === 'queued') { phase = 'QUEUED'; reason = 'Run queued; execution has not been observed' }
  else if (!selectedRunId && workspace) { phase = 'CREATED'; reason = 'Mission exists; no Run selected' }
  if (control) evidence.push(`run:${selectedRunId}:formalControl:${control.status}`)
  if (run?.lifecyclePhase) evidence.push(`run:${selectedRunId}:lifecyclePhase:${run.lifecyclePhase}`)
  if (run?.failureCode || run?.error?.code) evidence.push(`run:${selectedRunId}:failure:${run.failureCode || run.error?.code}`)
  if (run?.review) evidence.push(`run:${selectedRunId}:review:${run.review.subjectId || run.review.stepId || 'unknown'}`)
  const successorRunId = run?.lineage?.supersededByRunId || null
  const historical = status === 'superseded' || Boolean(successorRunId)
  // No currentRunId authority exists in the present Workspace contract. Do not
  // replace it with timestamps, selected flags, or absence of a successor edge.
  const unavailableReasons = [historical ? 'Historical Run is immutable' : 'Current Run authority NOT_OBSERVED; in-place controls disabled']
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
    phase, reason, isHistorical: historical, isCurrent: historical ? false : null, currentRunId: null,
    latestRunId: latest.length === 1 ? latest[0].id : null, successorRunId, isReadOnly: true,
    recommendedEditor, recommendedEntryId, recommendedInspector: inspector,
    availableActions: selectedRunId ? ['inspect', 'discuss', ...(['completed', 'succeeded', 'failed', 'cancelled', 'superseded'].includes(status) ? ['create_successor'] : [])] : ['inspect'],
    unavailableReasons, evidenceReferences: evidence,
    notObserved: [...(!run && selectedRunId ? ['runDetail'] : []), 'currentRunAuthority', ...(!control ? ['formalControl'] : []), 'checkpointRecoveryAuthorization'],
    deliverable, deliveryStatus: phase !== 'COMPLETED' ? 'NOT_COMPLETE' : deliverable ? 'READY' : 'MISSING',
    failure: phase === 'FAILED' ? { layer: failedStep ? 'Task' : run?.lifecyclePhase === 'planning' ? 'Planner' : 'Run (layer NOT_OBSERVED)',
      objectId: failedStep?.stepId || selectedRunId || 'unknown', reason, checkpoint: 'NOT_OBSERVED', sideEffects: 'NOT_OBSERVED' } : null
  }
}
