import type { RunActionCapabilities, WorkflowRun } from '@/services/api/agentos'

export const runCapabilityActions = ['canInspect', 'canDiscuss', 'canCancel', 'canReview', 'canExecuteFormalAction',
  'canResolveToolApproval', 'canAnswerPlanner', 'canCollaborate', 'canRetrySuccessor', 'canRerunSuccessor',
  'canDecideRevision', 'canApplyRevision', 'canDelete'] as const
export type RunCapabilityAction = typeof runCapabilityActions[number]
const active = new Set(['pending', 'planning', 'running', 'retrying', 'waiting_review'])
const terminal = new Set(['completed', 'failed', 'cancelled', 'superseded'])

/** Validate scope and comparison revision; selected/latest never grant offers. */
export function readRunCapabilities(value: RunActionCapabilities | null | undefined, missionId: string,
  runId: string | null, revision?: number, status?: string): RunActionCapabilities | null {
  if (!value || value.schemaVersion !== 1 || value.missionId !== missionId || value.runId !== runId
    || !Number.isInteger(value.runtimeRevision) || value.runtimeRevision < 0
    || (revision !== undefined && revision !== value.runtimeRevision) || (status !== undefined && status !== value.status)
    || !runCapabilityActions.every(action => typeof value[action] === 'boolean')
    || !active.has(value.status) && !terminal.has(value.status)
    || value.isExecutionActive !== active.has(value.status)
    || typeof value.isSuperseded !== 'boolean' || !value.lineage || typeof value.lineage !== 'object' || Array.isArray(value.lineage)
    || ((value.status === 'superseded' || value.lineage.supersededByRunId) && !value.isSuperseded)
    || !Array.isArray(value.formalActions) || !value.formalActions.every(action =>
      ['materialize', 'activate', 'handoff', 'permit', 'dispatch'].includes(action))
    || !Array.isArray(value.unavailableReasons) || !value.unavailableReasons.every(reason => reason
      && typeof reason.action === 'string' && typeof reason.code === 'string')) return null
  if (value.isSuperseded && runCapabilityActions.some(action => !['canInspect', 'canDiscuss', 'canDelete'].includes(action) && value[action])) return null
  if (value.canCancel && !value.isExecutionActive || value.canReview && value.status !== 'waiting_review'
    || value.canExecuteFormalAction && !['pending', 'planning'].includes(value.status)
    || value.canExecuteFormalAction !== (value.formalActions.length > 0)
    || value.canResolveToolApproval && value.status !== 'running'
    || value.canAnswerPlanner && value.status !== 'waiting_review'
    || value.canRetrySuccessor && (value.status !== 'failed' || !value.retryStepId)
    || value.canDecideRevision && !value.isExecutionActive || value.canApplyRevision && value.status !== 'cancelled'
    || value.canDelete && !terminal.has(value.status)) return null
  return value
}

export const runCapabilities = (run: WorkflowRun | null | undefined) => run && Number.isInteger(run.runtimeRevision)
  ? readRunCapabilities(run.actionCapabilities, run.missionId, run.runId, run.runtimeRevision, run.status) : null
