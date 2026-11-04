import type { WorkflowRun } from '@/services/api/agentos'
import type { FormalAction, FormalCommand } from '@/services/api/agentos/api/c2'

export const formalActionLabels: Record<FormalAction, string> = {
  materialize: '准备任务图', activate: '激活并保持暂停', handoff: '准备执行交接', permit: '申请执行许可', dispatch: '执行任务'
}

export interface FormalOperationSuccess {
  action: FormalAction
  operationId: string
  status: string
  dispatchId?: string
  missionId: string
  runId: string
}
export const validFormalReceipt = (action: FormalAction, operationId: string,
  receipt: { operationId: string; status: string; dispatchId?: string }) => {
  const statuses = { materialize: 'MATERIALIZED_INACTIVE', activate: 'ACTIVATED_PAUSED',
    handoff: 'STATE_PREPARED', permit: 'ISSUED', dispatch: 'ACCEPTED' }
  return receipt?.operationId === operationId && [statuses[action], 'IDEMPOTENT_REPLAY'].includes(receipt.status)
    && (action !== 'dispatch' || typeof receipt.dispatchId === 'string' && receipt.dispatchId.trim().length > 0)
}
const positive = (value: unknown): value is number => Number.isInteger(value) && Number(value) > 0
const reference = (value: unknown): value is string => typeof value === 'string' && value.length > 0
const graphReady = (run: WorkflowRun) => reference(run.formalControl?.graphId) && positive(run.formalControl?.graphVersion)

/** Only selects an offered action from a fresh authoritative snapshot. */
export const nextFormalAction = (run: WorkflowRun | null): FormalAction | null => {
  const c = run?.formalControl
  if (!run || !c || !['pending', 'planning'].includes(run.status) || c.dispatch) return null
  if (c.status === 'PLANNING_ACCEPTED' && reference(c.commitId) && positive(c.commitmentRevision)) return 'materialize'
  if (!graphReady(run)) return null
  if (['MATERIALIZED_INACTIVE', 'ACTIVATION_PREPARED'].includes(c.status) && reference(c.materializationId)) return 'activate'
  if (c.status === 'ACTIVATED_PAUSED') {
    if (!c.handoffId && reference(c.activationId)) return 'handoff'
    if (c.handoffStatus === 'STATE_PREPARED' && reference(c.handoffId) && !c.permitIssued) return 'permit'
  }
  if (c.status === 'ACTIVATED' && c.permitStatus === 'ISSUED' && c.dispatchEnabled === true && c.dispatchEligible === true
      && reference(c.permitId) && Number.isInteger(run.runtimeRevision) && Number(run.runtimeRevision) >= 0) return 'dispatch'
  return null
}

export const formalSource = (run: WorkflowRun, action: FormalAction) => {
  const c = run.formalControl!
  return JSON.stringify([run.missionId, run.runId, action,
    { materialize: c.commitId, activate: c.materializationId, handoff: c.activationId, permit: c.handoffId, dispatch: c.permitId }[action],
    c.graphId, c.graphVersion])
}

interface RetryHint { operationId: string; source: string; runtimeRevision?: number }
/** Cache only retry identity/comparison hints. Never hydrate an executable request body. */
export const prepareFormalCommand = (run: WorkflowRun, action: FormalAction, storage: Storage): FormalCommand => {
  if (nextFormalAction(run) !== action) throw new Error('正式状态不允许此操作，请刷新 Run。')
  const source = formalSource(run, action)
  const key = `agentos.c2.operation.v1:${source}`
  const saved = storage.getItem(key)
  let hint: RetryHint
  if (saved) {
    hint = JSON.parse(saved)
    if (hint.source !== source || !/^wb-[a-f0-9-]{36}$/.test(hint.operationId)
        || (action === 'dispatch' && (!Number.isInteger(hint.runtimeRevision) || Number(hint.runtimeRevision) < 0))) {
      throw new Error('操作重试记录损坏，已阻断控制操作。')
    }
  } else {
    hint = { source, operationId: `wb-${crypto.randomUUID()}`, runtimeRevision: run.runtimeRevision }
    storage.setItem(key, JSON.stringify(hint)) // Persist before sending; storage failure is fail-closed.
  }
  const c = run.formalControl!
  const operationId = hint.operationId
  const graph = { expectedGraphId: c.graphId!, expectedGraphVersion: c.graphVersion! }
  switch (action) {
    case 'materialize': return { operationId, commitId: c.commitId!, expectedCommitmentRevision: c.commitmentRevision! }
    case 'activate': return { operationId, materializationId: c.materializationId!, ...graph }
    case 'handoff': return { operationId, activationId: c.activationId!, ...graph }
    case 'permit': return { operationId, handoffId: c.handoffId!, ...graph }
    case 'dispatch': return { operationId, expectedPermitId: c.permitId!, ...graph, expectedRuntimeRevision: hint.runtimeRevision! }
  }
}
