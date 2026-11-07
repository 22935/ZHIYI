import type { SingleStepRetryRequest, WorkflowRerunRequest } from '@/services/api/agentos'
import { canonicalLaunchJson } from '@/features/mission/command'

type RecoveryCommand = { kind: 'retry'; stepId: string; payload: SingleStepRetryRequest }
  | { kind: 'rerun'; payload: WorkflowRerunRequest }
export type RecoveryIdentity = RecoveryCommand & { missionId: string; sourceRunId: string; fingerprint: string }
const keyFor = (missionId: string, sourceRunId: string) => {
  if (!localStorage.getItem('userId')) throw new Error('本机身份尚未就绪，禁止恢复操作')
  return `workbench.recovery.v1:${encodeURIComponent(JSON.stringify([localStorage.getItem('tenantId'), localStorage.getItem('userId'), missionId, sourceRunId]))}`
}
const fingerprint = (value: Omit<RecoveryIdentity, 'fingerprint'>) => canonicalLaunchJson(value)
function assertCommand(value: RecoveryIdentity, missionId: string, sourceRunId: string) {
  const { fingerprint: saved, ...command } = value
  if (value.missionId !== missionId || value.sourceRunId !== sourceRunId || !value.payload?.clientRequestId
    || saved !== fingerprint(command) || (value.kind !== 'retry' && value.kind !== 'rerun')
    || (value.kind === 'retry' && (!value.stepId || value.payload.mode !== 'successor_run'))
    || (value.kind === 'rerun' && value.payload.sourceRunId !== sourceRunId)) throw new Error('恢复快照身份损坏，禁止生成新身份重试')
}
export function pendingRunRecovery(missionId: string, sourceRunId: string, storage: Storage): RecoveryIdentity | null {
  const raw = storage.getItem(keyFor(missionId, sourceRunId))
  if (!raw) return null
  const value = JSON.parse(raw) as RecoveryIdentity
  assertCommand(value, missionId, sourceRunId)
  return value
}
export function beginRunRecovery(missionId: string, sourceRunId: string, command: RecoveryCommand, storage: Storage): RecoveryIdentity {
  const next = { ...command, missionId, sourceRunId }
  const identity = { ...next, fingerprint: fingerprint(next) } as RecoveryIdentity
  assertCommand(identity, missionId, sourceRunId)
  const saved = pendingRunRecovery(missionId, sourceRunId, storage)
  if (saved && saved.fingerprint !== identity.fingerprint) throw new Error('原恢复结果未确认，必须重试原操作')
  storage.setItem(keyFor(missionId, sourceRunId), JSON.stringify(saved || identity))
  return saved || identity
}
export function completeRunRecovery(identity: RecoveryIdentity, storage: Storage) {
  const saved = pendingRunRecovery(identity.missionId, identity.sourceRunId, storage)
  if (saved?.fingerprint === identity.fingerprint) storage.removeItem(keyFor(identity.missionId, identity.sourceRunId))
}
