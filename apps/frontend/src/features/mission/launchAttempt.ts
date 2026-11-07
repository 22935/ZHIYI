import { workflowApi, type AsyncWorkflowStartRequest } from '@/services/api/workflow'
import { launchMission, missionLaunchResult, type MissionLaunchOptions, type MissionLaunchResult } from './launch'
import { prepareMissionLaunch } from './admission'
import { assertMissionLaunchCommand, canonicalLaunchJson, cloneLaunchValue, missionCommandFingerprint, restoreMissionLaunchCommand, type MissionLaunchCommand } from './command'
import { missionLaunchConflict, type MissionLaunchConflict } from './conflict'

export const createLaunchRequestId = () => globalThis.crypto?.randomUUID?.()
  || `launch-${Date.now()}-${Math.random().toString(36).slice(2)}`
export class MissionLaunchStateError extends Error {
  constructor(public readonly code: 'BUSY' | 'IDENTITY_CONFLICT' | 'RECONCILIATION_REQUIRED' | 'EXPIRED' | 'CORRUPT' | 'SENSITIVE_INPUT', message: string) { super(message); this.name = 'MissionLaunchStateError' }
}
export interface LaunchAttemptIdentity {
  schemaVersion: 2
  operationId: string
  clientRequestId: string
  entry: MissionLaunchCommand['entry']
  commandSnapshot: AsyncWorkflowStartRequest
  requestSnapshot: AsyncWorkflowStartRequest
  requestFingerprint: string
  wireFingerprint: string
  materialPreparationState: 'pending' | 'ready' | 'uncertain'
  submissionState: 'ready' | 'submitting' | 'uncertain' | 'conflict' | 'accepted'
  conflict: MissionLaunchConflict
  createdAt: string
  updatedAt: string
  missionId?: string
  runId?: string
}
type AttemptOptions = MissionLaunchOptions & { operationId?: string }
const active = new Map<string, { operationId: string; promise: Promise<MissionLaunchResult> }>()
const MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000
function assertNoCredentials(value: unknown): void {
  if (!value || typeof value !== 'object') return
  for (const [key, item] of Object.entries(value)) {
    if (/^(apikey|authorization|password|accesstoken|refreshtoken|providerconnections|clientsecret)$/i.test(key.replace(/[_-]/g, ''))) {
      throw new MissionLaunchStateError('SENSITIVE_INPUT', '任务提交中包含连接凭据，禁止持久化。')
    }
    assertNoCredentials(item)
  }
}

// One durable submission identity per owner/entry slot. Execution facts are
// read from server creation anchors, never inferred from this retry cache.
export function createMissionLaunchAttempt(options: { slot?: string; storage?: Storage; key?: string } = {}) {
  const storage = options.storage || sessionStorage
  const slot = options.slot || 'workbench'
  const ownerScope = () => {
    if (!localStorage.getItem('userId')) throw new MissionLaunchStateError('IDENTITY_CONFLICT', '本机身份尚未就绪，禁止恢复或新建提交。')
    return `${localStorage.getItem('tenantId') || ''}:${localStorage.getItem('userId') || 'session'}`
  }
  const owner = ownerScope()
  const key = options.key || `mission.launch.attempt.v2:${encodeURIComponent(owner)}:${slot}`
  const operationKey = (id: string) => `mission.launch.operation.v2:${encodeURIComponent(owner)}:${id}`
  const assertOwner = () => {
    if (ownerScope() !== owner) {
      throw new MissionLaunchStateError('IDENTITY_CONFLICT', '本机身份已改变，禁止提交其他身份的快照。')
    }
  }
  const save = (identity: LaunchAttemptIdentity) => {
    assertOwner()
    assertNoCredentials(identity)
    identity.updatedAt = new Date().toISOString()
    identity.wireFingerprint = canonicalLaunchJson(identity.requestSnapshot)
    storage.setItem(operationKey(identity.operationId), JSON.stringify(identity))
    storage.setItem(key, JSON.stringify({ operationId: identity.operationId }))
  }
  const read = (): LaunchAttemptIdentity | null => {
    assertOwner()
    const raw = storage.getItem(key)
    if (!raw) return null
    try {
      const pointer = JSON.parse(raw)
      const identity = JSON.parse(storage.getItem(operationKey(pointer.operationId)) || 'null') as LaunchAttemptIdentity
      if (!identity || identity.operationId !== pointer.operationId) throw new Error('missing operation snapshot')
      assertNoCredentials(identity)
      if (identity.schemaVersion !== 2 || !identity.operationId || identity.operationId !== identity.clientRequestId
        || identity.requestSnapshot?.clientRequestId !== identity.clientRequestId
        || canonicalLaunchJson(identity.requestSnapshot) !== identity.wireFingerprint
        || missionCommandFingerprint(restoreMissionLaunchCommand(identity.entry, identity.commandSnapshot)) !== identity.requestFingerprint
        || !Number.isFinite(Date.parse(identity.createdAt)) || !Number.isFinite(Date.parse(identity.updatedAt))
        || !['pending', 'ready', 'uncertain'].includes(identity.materialPreparationState)
        || !['ready', 'submitting', 'uncertain', 'conflict', 'accepted'].includes(identity.submissionState)) throw new Error('invalid snapshot')
      return identity
    } catch { throw new MissionLaunchStateError('CORRUPT', '任务提交快照损坏，禁止自动重建身份。') }
  }
  const begin = (command: MissionLaunchCommand, operationId?: string): LaunchAttemptIdentity => {
    assertMissionLaunchCommand(command)
    assertNoCredentials(command.request)
    const existing = read()
    if (existing) {
      if (operationId && operationId !== existing.operationId) throw new MissionLaunchStateError('BUSY', '入口已有另一个待确认操作。')
      if (missionCommandFingerprint(command) !== existing.requestFingerprint) throw new MissionLaunchStateError(
        operationId ? 'IDENTITY_CONFLICT' : 'BUSY', '已有未确认提交；请恢复原操作，不能用新任务替换原身份。')
      return existing
    }
    if (operationId && storage.getItem(operationKey(operationId))) {
      const shared = JSON.parse(storage.getItem(operationKey(operationId))!) as LaunchAttemptIdentity
      if (shared.requestFingerprint !== missionCommandFingerprint(command)) throw new MissionLaunchStateError('IDENTITY_CONFLICT', '相同操作身份对应不同请求。')
      storage.setItem(key, JSON.stringify({ operationId }))
      return read()!
    }
    let legacyRequest: AsyncWorkflowStartRequest | undefined
    let legacyMaterialUncertain = false
    if (slot.startsWith('conversation:')) {
      const conversationId = slot.slice('conversation:'.length)
      const hint = storage.getItem(`chat.workflow_submission.${conversationId}`)
      if (hint) {
        const legacy = JSON.parse(hint)
        operationId ||= legacy.clientRequestId
        const cached = storage.getItem(`mission.launch.request.v1:${conversationId}:${operationId}`)
        if (!cached) throw new MissionLaunchStateError('RECONCILIATION_REQUIRED', '旧提交缺少原始请求快照，须人工核对，禁止换身份重建。')
        const oldSnapshot = JSON.parse(cached)
        legacyRequest = oldSnapshot.request
        legacyMaterialUncertain = oldSnapshot.materialState === 'uncertain'
      }
    }
    const id = operationId || createLaunchRequestId()
    const now = new Date().toISOString()
    const identity: LaunchAttemptIdentity = {
      schemaVersion: 2, operationId: id, clientRequestId: id, entry: command.entry,
      commandSnapshot: cloneLaunchValue(command.request), requestSnapshot: cloneLaunchValue(legacyRequest || command.request),
      requestFingerprint: missionCommandFingerprint(command), wireFingerprint: '',
      materialPreparationState: legacyMaterialUncertain ? 'uncertain' : legacyRequest ? 'ready' : 'pending', submissionState: legacyRequest ? 'uncertain' : 'ready',
      conflict: null, createdAt: now, updatedAt: now
    }
    identity.requestSnapshot.clientRequestId = id
    save(identity)
    return identity
  }
  const complete = (operationId: string) => {
    const identity = read()
    if (!identity) return
    if (identity.operationId !== operationId || identity.submissionState !== 'accepted') throw new MissionLaunchStateError('IDENTITY_CONFLICT', '只能完成已确认的原始操作。')
    const pointerPrefix = `mission.launch.attempt.v2:${encodeURIComponent(owner)}:`
    const pointers = Array.from({ length: storage.length }, (_, index) => storage.key(index)).filter((name): name is string => Boolean(name) && (name === key || name.startsWith(pointerPrefix)))
    for (const pointerKey of pointers) {
      if (JSON.parse(storage.getItem(pointerKey) || 'null')?.operationId === operationId) storage.removeItem(pointerKey)
    }
    storage.removeItem(operationKey(operationId))
    if (slot.startsWith('conversation:')) {
      const conversationId = slot.slice('conversation:'.length)
      const hintKey = `chat.workflow_submission.${conversationId}`
      const hint = storage.getItem(hintKey)
      if (hint && JSON.parse(hint).clientRequestId === operationId) storage.removeItem(hintKey)
      storage.removeItem(`mission.launch.request.v1:${conversationId}:${operationId}`)
    }
  }
  const reconcile = async (callOptions?: MissionLaunchOptions) => {
    const identity = read()
    if (!identity) throw new MissionLaunchStateError('RECONCILIATION_REQUIRED', '没有可核对的启动操作。')
    return workflowApi.reconcileMissionLaunch(cloneLaunchValue(identity.requestSnapshot), callOptions)
  }
  const resume = (operationId: string, callOptions?: MissionLaunchOptions): Promise<MissionLaunchResult> => {
    const identity = read()
    if (!identity || identity.operationId !== operationId) return Promise.reject(new MissionLaunchStateError('IDENTITY_CONFLICT', '原始提交身份不匹配。'))
    const activeKey = operationKey(operationId)
    const running = active.get(activeKey)
    if (running) return running.operationId === operationId ? running.promise
      : Promise.reject(new MissionLaunchStateError('BUSY', '入口正在处理另一个操作。'))
    const execute = async () => {
      if (callOptions?.signal?.aborted) throw new DOMException('Mission launch aborted', 'AbortError')
      const accept = (run: MissionLaunchResult['run']) => {
        const result = missionLaunchResult(run, identity.requestSnapshot)
        if ((identity.missionId && identity.missionId !== result.missionId) || (identity.runId && identity.runId !== result.runId)) {
          throw new MissionLaunchStateError('IDENTITY_CONFLICT', '已确认的创建身份发生变化，禁止覆盖。')
        }
        identity.submissionState = 'accepted'; identity.missionId = result.missionId; identity.runId = result.runId
        save(identity)
        return result
      }
      if (identity.materialPreparationState === 'uncertain') throw new MissionLaunchStateError('RECONCILIATION_REQUIRED', 'Material 创建结果未确认；保留原操作，禁止重复创建材料。')
      if (identity.submissionState !== 'ready' || Date.now() - Date.parse(identity.updatedAt) > MAX_AGE_MS) {
        const receipt = await reconcile(callOptions)
        if (receipt.status === 'CREATED') {
          if (receipt.run.missionId !== receipt.missionId || receipt.run.runId !== receipt.runId) throw new MissionLaunchStateError('CORRUPT', '创建对账响应身份不一致。')
          return accept(receipt.run)
        }
        if (Date.now() - Date.parse(identity.updatedAt) > MAX_AGE_MS) throw new MissionLaunchStateError('EXPIRED', '提交快照已过期，已对账但不会自动重建或删除。')
        if (identity.submissionState === 'conflict' || !['NOT_FOUND', 'CREATING'].includes(receipt.status)) {
          identity.submissionState = 'conflict'; save(identity)
          throw new MissionLaunchStateError('RECONCILIATION_REQUIRED', `原操作需要核对：${receipt.status}`)
        }
      }
      if (identity.materialPreparationState === 'pending') {
        const material = identity.requestSnapshot.input?.materialText
        if (typeof material === 'string' && material.trim()) {
          identity.materialPreparationState = 'uncertain'; save(identity)
          const manifest = await workflowApi.createMaterial(material.trim(), 'text/plain')
          if (!manifest?.manifestId) throw new MissionLaunchStateError('RECONCILIATION_REQUIRED', 'Material 响应缺少身份。')
          identity.requestSnapshot.materialRefs = [...(identity.requestSnapshot.materialRefs || []), manifest.manifestId]
          delete identity.requestSnapshot.input!.materialText
        }
        identity.materialPreparationState = 'ready'; save(identity)
      }
      if (callOptions?.signal?.aborted) throw new DOMException('Mission launch aborted', 'AbortError')
      identity.submissionState = 'submitting'; save(identity)
      try {
        return accept((await launchMission(prepareMissionLaunch(operationId, identity.requestSnapshot), callOptions)).run)
      } catch (error) {
        identity.conflict = missionLaunchConflict(error)
        identity.submissionState = identity.conflict === 'ATTACHMENT_NOT_READY' ? 'ready' : identity.conflict ? 'conflict' : 'uncertain'
        save(identity)
        throw error
      }
    }
    const promise = Promise.resolve().then(execute).finally(() => { if (active.get(activeKey)?.promise === promise) active.delete(activeKey) })
    active.set(activeKey, { operationId, promise })
    return promise
  }
  const launch = (command: MissionLaunchCommand, callOptions?: AttemptOptions): Promise<MissionLaunchResult> => {
    try { return resume(begin(command, callOptions?.operationId).operationId, callOptions?.signal ? { signal: callOptions.signal } : undefined) }
    catch (error) { return Promise.reject(error) }
  }
  return { begin, launch, resume, reconcile, complete, pending: read }
}
