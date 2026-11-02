import type { RunActionCapabilities } from '@/services/api/agentos'

/** API boundary fixture: scenario-specific evidence offers are explicit overrides. */
export function capabilitiesFixture(runId: string, missionId: string, status = 'running', runtimeRevision = 1,
  extra: Partial<RunActionCapabilities> = {}): RunActionCapabilities {
  const active = ['pending', 'planning', 'running', 'retrying', 'waiting_review'].includes(status)
  return { schemaVersion: 1, runId, missionId, status, runtimeRevision, lineage: {},
    isExecutionActive: active, isSuperseded: status === 'superseded', canInspect: true, canDiscuss: true,
    canCancel: active, canCollaborate: active, canReview: false, canAnswerPlanner: false,
    canExecuteFormalAction: false, formalActions: [], canResolveToolApproval: false,
    canRetrySuccessor: false, retryStepId: null, canRerunSuccessor: ['failed', 'completed', 'cancelled'].includes(status),
    canDecideRevision: false, canApplyRevision: false, canDelete: ['failed', 'completed', 'cancelled', 'superseded'].includes(status),
    unavailableReasons: [], ...extra }
}
