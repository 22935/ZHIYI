import type { DeepReadonly } from 'vue'
import type { WorkflowRun, WorkflowProgress } from '@/services/api/agentos'
import { runCapabilities } from '@/workbench/runtime/runCapabilities'
export type ProgressObservationState = 'TRUSTED' | 'RECONCILING' | 'STALE' | 'IDENTITY_MISMATCH' | 'UNAVAILABLE'
export type LifecyclePhase = 'CREATED' | 'QUEUED' | 'PLANNING' | 'AWAITING_CONFIRMATION'
  | 'ACTIVATED_PAUSED' | 'READY_TO_DISPATCH' | 'DISPATCHED' | 'RUNNING' | 'WAITING_REVIEW'
  | 'RECOVERING' | 'FAILED' | 'COMPLETED' | 'CANCELLED' | 'SUPERSEDED' | 'UNKNOWN'

export const lifecycleLabels: Record<LifecyclePhase, string> = {
  CREATED: '任务已创建', QUEUED: '排队中', PLANNING: '规划中', AWAITING_CONFIRMATION: '等待确认',
  ACTIVATED_PAUSED: '已激活，等待执行', READY_TO_DISPATCH: '等待正式派发', DISPATCHED: '已派发，等待运行',
  RUNNING: '执行中', WAITING_REVIEW: '等待人工审核', RECOVERING: '恢复中', FAILED: '运行失败',
  COMPLETED: '已完成', CANCELLED: '已取消', SUPERSEDED: '已被后续运行替代', UNKNOWN: '状态待确认'
}
export function mapRunPhase(rawStatus: string | null, run: WorkflowRun | null, selectedRunId: string | null, hasMission: boolean) {
  const status = rawStatus?.toLowerCase() || 'unknown'
  const control = run?.formalControl
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
  else if (!selectedRunId && hasMission) { phase = 'CREATED'; reason = 'Mission exists; no Run selected' }
  return { phase, reason }
}
export function projectRunLifecycle(input: { missionId: string; runId: string; run?: WorkflowRun | null; progress?: DeepReadonly<WorkflowProgress> | null }) {
  const { missionId, runId } = input
  const mismatch = Boolean(input.run && (input.run.runId !== runId || input.run.missionId !== missionId))
  const run = mismatch ? null : input.run || null
  const candidate = input.progress
  const progressMatches = candidate?.runId === runId && candidate?.missionId === missionId
  const revision = (candidate as { runtimeRevision?: number } | null)?.runtimeRevision
  const stale = Boolean(run && revision !== undefined && run.runtimeRevision !== undefined && revision < run.runtimeRevision)
  // Keep same-identity observations for diagnostics, but expose only reconciled data to presentation.
  const progressObservation = progressMatches && !mismatch ? candidate ?? null : null
  const identityMismatch = mismatch || Boolean(candidate && !progressMatches)
  const capabilitiesInvalid = Boolean(run?.actionCapabilities && !runCapabilities(run))
  const conflict = Boolean(run && progressObservation && !stale && (progressObservation.status !== run.status
    || revision !== undefined && revision > (run.runtimeRevision ?? -1)))
  const progressObservationState: ProgressObservationState = identityMismatch ? 'IDENTITY_MISMATCH'
    : stale ? 'STALE' : conflict ? 'RECONCILING' : progressObservation ? 'TRUSTED' : 'UNAVAILABLE'
  const progress = progressObservationState === 'TRUSTED' ? progressObservation : null
  const rawStatus = run?.status || progress?.status || null
  const mapped = mapRunPhase(rawStatus, run, runId, Boolean(missionId))
  const synchronizationState = identityMismatch ? 'IDENTITY_MISMATCH'
    : capabilitiesInvalid || conflict ? 'RECONCILING' : !run && !progress ? 'UNAVAILABLE'
    : !run || !runCapabilities(run) || stale ? 'PARTIAL' : 'SYNCED'
  return { missionId, runId, rawStatus, normalizedStatus: rawStatus === 'succeeded' ? 'completed' : rawStatus || 'unknown',
    ...mapped, phaseLabel: lifecycleLabels[mapped.phase], statusLabel: lifecycleLabels[mapped.phase],
    statusSource: run ? 'RUN' : progress ? 'PROGRESS_TEMPORARY' : 'UNAVAILABLE', synchronizationState,
    isTerminal: ['COMPLETED', 'FAILED', 'CANCELLED', 'SUPERSEDED'].includes(mapped.phase),
    requiresAttention: ['WAITING_REVIEW', 'FAILED', 'AWAITING_CONFIRMATION', 'READY_TO_DISPATCH'].includes(mapped.phase),
    progress, progressObservation, progressObservationState }
}

export type RunLifecycleProjection = ReturnType<typeof projectRunLifecycle>
