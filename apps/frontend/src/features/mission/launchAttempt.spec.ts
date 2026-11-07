import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { workflowApi } from '@/services/api/workflow'
import { createMissionLaunchAttempt } from './launchAttempt'
import { workbenchLaunchCommand, conversationLaunchCommand, missionCommandFingerprint, restoreMissionLaunchCommand } from './command'
import { createNativeWorkbenchDraft } from '@/features/acg/workbench'

vi.mock('@/services/api/workflow', () => ({ workflowApi: { startWorkflowAsync: vi.fn(), createMaterial: vi.fn(), reconcileMissionLaunch: vi.fn() } }))
const run = { missionId: 'mission', runId: 'run', status: 'pending' } as any
const command = (goal = '目标') => workbenchLaunchCommand({ ...createNativeWorkbenchDraft(), taskGoal: goal, materialText: '材料' }, [], { attachmentIds: ['att'] })
const calls = () => vi.mocked(workflowApi.startWorkflowAsync).mock.calls

describe('Mission launch operation authority', () => {
  beforeEach(() => {
    vi.resetAllMocks(); sessionStorage.clear(); localStorage.clear(); localStorage.setItem('userId', 'local-owner')
    vi.mocked(workflowApi.createMaterial).mockResolvedValue({ manifestId: 'sealed' } as any)
    vi.mocked(workflowApi.startWorkflowAsync).mockResolvedValue(run)
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'NOT_FOUND' })
  })
  afterEach(() => vi.useRealTimers())
  it('retries exact wire data after timeout and NOT_FOUND reconciliation without recreating Material', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(new Error('lost'))
    const attempt = createMissionLaunchAttempt()
    await expect(attempt.launch(command())).rejects.toThrow('lost')
    const first = calls()[0][0]
    const result = await attempt.launch(command())
    expect(calls()[1][0]).toEqual(first)
    expect(first).toMatchObject({ materialRefs: ['sealed'], attachmentIds: ['att'] })
    expect(first.input).not.toHaveProperty('materialText')
    expect(result.clientRequestId).toBe(first.clientRequestId)
    expect(workflowApi.createMaterial).toHaveBeenCalledTimes(1)
  })
  it('recovers a lost success from server without submitting a second create', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(new Error('lost'))
    const attempt = createMissionLaunchAttempt()
    await expect(attempt.launch(command())).rejects.toThrow()
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'CREATED', missionId: 'mission', runId: 'run', run })
    const result = await createMissionLaunchAttempt().resume(attempt.pending()!.operationId)
    expect(result.runId).toBe('run')
    expect(calls()).toHaveLength(1)
    expect(attempt.pending()!.submissionState).toBe('accepted')
    attempt.complete(result.clientRequestId)
    expect(attempt.pending()).toBeNull()
  })
  it('coalesces identical operation IDs across component reconstruction', async () => {
    let resolve: (value: any) => void
    vi.mocked(workflowApi.startWorkflowAsync).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    const attempt = createMissionLaunchAttempt()
    const first = attempt.launch(command(), { operationId: 'operation' })
    const second = createMissionLaunchAttempt().launch(command(), { operationId: 'operation' })
    expect(first).toBe(second)
    await vi.waitFor(() => expect(calls()).toHaveLength(1))
    resolve!(run); await first
  })
  it('returns BUSY for a different operation while one is in flight', async () => {
    let resolve: (value: any) => void
    vi.mocked(workflowApi.startWorkflowAsync).mockImplementationOnce(() => new Promise(r => { resolve = r }))
    const attempt = createMissionLaunchAttempt()
    const first = attempt.launch(command(), { operationId: 'first' })
    await expect(attempt.launch(command('另一个任务'), { operationId: 'second' })).rejects.toMatchObject({ code: 'BUSY' })
    await vi.waitFor(() => expect(calls()).toHaveLength(1))
    resolve!(run); await first
  })
  it('rejects a changed request under the same operation ID', async () => {
    const attempt = createMissionLaunchAttempt()
    attempt.begin(command(), 'operation')
    await expect(attempt.launch(command('新语义'), { operationId: 'operation' })).rejects.toMatchObject({ code: 'IDENTITY_CONFLICT' })
    expect(calls()).toHaveLength(0)
  })
  it('requires completion acknowledgement before accepting a new intent', async () => {
    const attempt = createMissionLaunchAttempt()
    const first = await attempt.launch(command())
    await expect(attempt.launch(command('new'))).rejects.toMatchObject({ code: 'BUSY' })
    attempt.complete(first.clientRequestId)
    expect((await attempt.launch(command('new'))).clientRequestId).not.toBe(first.clientRequestId)
  })
  it.each(['workbench', 'legacy-acg', 'conversation:c'])('persists the original operation across unmount for %s', async slot => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(new Error('offline'))
    const attempt = createMissionLaunchAttempt({ slot })
    await expect(attempt.launch(command())).rejects.toThrow()
    const id = attempt.pending()!.operationId
    const restored = createMissionLaunchAttempt({ slot })
    expect(restored.pending()!.operationId).toBe(id)
    await restored.resume(id)
    expect(calls()[1][0]).toEqual(calls()[0][0])
    expect(workflowApi.createMaterial).toHaveBeenCalledTimes(1)
  })
  it('never repeats a Material side effect whose response was lost, including after reconstruction', async () => {
    vi.mocked(workflowApi.createMaterial).mockRejectedValueOnce(new Error('material lost'))
    const attempt = createMissionLaunchAttempt()
    await expect(attempt.launch(command())).rejects.toThrow('material lost')
    await expect(createMissionLaunchAttempt().resume(attempt.pending()!.operationId)).rejects.toMatchObject({ code: 'RECONCILIATION_REQUIRED' })
    expect(workflowApi.createMaterial).toHaveBeenCalledTimes(1)
    expect(calls()).toHaveLength(0)
  })
  it('retries Mission-created/Run-not-prepared under the same server creation anchor', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce({ response: { status: 503 } })
    const attempt = createMissionLaunchAttempt()
    await expect(attempt.launch(command())).rejects.toBeDefined()
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'CREATING', missionId: 'mission' })
    await attempt.resume(attempt.pending()!.operationId)
    expect(calls()[1][0]).toEqual(calls()[0][0])
  })
  it('allows attachment-not-ready retries with the original request and ID', async () => {
    const failure = { response: { status: 409, data: { detail: { code: 'ATTACHMENT_NOT_READY' } } } }
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(failure)
    const attempt = createMissionLaunchAttempt()
    await expect(attempt.launch(command())).rejects.toBe(failure)
    await attempt.resume(attempt.pending()!.operationId)
    expect(calls()[1][0]).toEqual(calls()[0][0])
  })
  it.each([undefined, 'CLIENT_REQUEST_ID_CONFLICT', 'MISSION_SEMANTIC_CONFLICT', 'OTHER_BUSINESS'])('409 %s preserves identity and fails closed after NOT_FOUND', async code => {
    const failure = { response: { status: 409, headers: { 'x-mission-launch-conflict': code } } }
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(failure)
    const attempt = createMissionLaunchAttempt()
    await expect(attempt.launch(command())).rejects.toBe(failure)
    const original = attempt.pending()!
    await expect(attempt.resume(original.operationId)).rejects.toMatchObject({ code: 'RECONCILIATION_REQUIRED' })
    expect(attempt.pending()!.clientRequestId).toBe(original.clientRequestId)
    expect(calls()).toHaveLength(1)
  })
  it('reconciles a semantic conflict to its confirmed result without creating a second Mission', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce({ response: { status: 409, headers: { 'x-mission-launch-conflict': 'MISSION_SEMANTIC_CONFLICT' } } })
    const attempt = createMissionLaunchAttempt()
    await expect(attempt.launch(command())).rejects.toBeDefined()
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'CREATED', missionId: 'mission', runId: 'run', run })
    expect((await attempt.resume(attempt.pending()!.operationId)).runId).toBe('run')
    expect(calls()).toHaveLength(1)
  })
  it('does not start material preparation when already aborted', async () => {
    const controller = new AbortController(); controller.abort()
    await expect(createMissionLaunchAttempt().launch(command(), { signal: controller.signal })).rejects.toMatchObject({ name: 'AbortError' })
    expect(workflowApi.createMaterial).not.toHaveBeenCalled()
    expect(calls()).toHaveLength(0)
  })
  it('quarantines expired snapshots without deleting or rebuilding them', async () => {
    vi.useFakeTimers()
    const attempt = createMissionLaunchAttempt()
    const original = attempt.begin(command())
    vi.setSystemTime(Date.now() + 8 * 24 * 60 * 60 * 1000)
    await expect(attempt.resume(original.operationId)).rejects.toMatchObject({ code: 'EXPIRED' })
    expect(attempt.pending()!.operationId).toBe(original.operationId)
    expect(calls()).toHaveLength(0)
  })
  it('blocks credential-bearing plugin data before persistence', async () => {
    const unsafe = restoreMissionLaunchCommand('workbench', { ...command().request, input: { pluginData: { apiKey: 'never-persist' } } })
    await expect(createMissionLaunchAttempt().launch(unsafe)).rejects.toMatchObject({ code: 'SENSITIVE_INPUT' })
    expect(JSON.stringify(sessionStorage)).not.toContain('never-persist')
    expect(calls()).toHaveLength(0)
  })
  it('does not send an old Home snapshot after local identity changes', async () => {
    localStorage.setItem('userId', 'first')
    const attempt = createMissionLaunchAttempt(); const identity = attempt.begin(command())
    localStorage.setItem('userId', 'second')
    expect(() => attempt.resume(identity.operationId)).toThrow('本机身份已改变')
    expect(calls()).toHaveLength(0)
  })
  it('canonicalizes object order and set-like scope/attachment refs while freezing wire ordering', () => {
    const first = restoreMissionLaunchCommand('workbench', { ...command().request, enabledPluginIds: ['b', 'a'], input: { y: 2, x: 1 } })
    const second = restoreMissionLaunchCommand('workbench', { ...first.request, title: 'display changed', enabledPluginIds: ['a', 'b'], input: { x: 1, y: 2 } })
    expect(missionCommandFingerprint(first)).toBe(missionCommandFingerprint(second))
    const attempt = createMissionLaunchAttempt(); const original = attempt.begin(first)
    expect(attempt.begin(second).requestSnapshot).toEqual(original.requestSnapshot)
  })
  it('shares one canonical snapshot and one in-flight submission across entry pointers for the same operation', async () => {
    let accept: (value: any) => void
    vi.mocked(workflowApi.startWorkflowAsync).mockImplementationOnce(() => new Promise(resolve => { accept = resolve }))
    const first = createMissionLaunchAttempt({ slot: 'one' })
    const second = createMissionLaunchAttempt({ slot: 'two' })
    const submitted = first.launch(command(), { operationId: 'shared-operation' })
    expect(second.launch(command(), { operationId: 'shared-operation' })).toBe(submitted)
    expect(Object.keys(sessionStorage).filter(key => key.startsWith('mission.launch.operation.v2:'))).toHaveLength(1)
    await vi.waitFor(() => expect(calls()).toHaveLength(1))
    accept!(run); await submitted
    first.complete('shared-operation')
    expect(second.pending()).toBeNull()
  })
  it('migrates the original legacy request without rebuilding its identity or semantics', async () => {
    const original = { ...command().request, clientRequestId: 'legacy-operation' }
    sessionStorage.setItem('chat.workflow_submission.c', JSON.stringify({ conversationId: 'c', text: '目标', clientRequestId: 'legacy-operation' }))
    sessionStorage.setItem('mission.launch.request.v1:c:legacy-operation', JSON.stringify({ request: original, materialState: 'uncertain' }))
    const attempt = createMissionLaunchAttempt({ slot: 'conversation:c' })
    await expect(attempt.launch(command())).rejects.toMatchObject({ code: 'RECONCILIATION_REQUIRED' })
    expect(attempt.pending()!.requestSnapshot).toEqual(original)
    expect(workflowApi.createMaterial).not.toHaveBeenCalled()
    expect(calls()).toHaveLength(0)
    expect(sessionStorage.getItem('chat.workflow_submission.c')).not.toBeNull()
  })
  it('fails closed on legacy identity without an original snapshot', async () => {
    sessionStorage.setItem('chat.workflow_submission.c', JSON.stringify({ conversationId: 'c', text: '目标', clientRequestId: 'legacy-operation' }))
    await expect(createMissionLaunchAttempt({ slot: 'conversation:c' }).launch(command())).rejects.toMatchObject({ code: 'RECONCILIATION_REQUIRED' })
    expect(calls()).toHaveLength(0)
  })
  it('refuses to overwrite a confirmed Mission/Run identity with an inconsistent reconciliation result', async () => {
    const attempt = createMissionLaunchAttempt()
    const accepted = await attempt.launch(command())
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'CREATED', missionId: 'other-mission', runId: 'other-run', run: { ...run, missionId: 'other-mission', runId: 'other-run' } })
    await expect(attempt.resume(accepted.clientRequestId)).rejects.toMatchObject({ code: 'IDENTITY_CONFLICT' })
    expect(attempt.pending()!.missionId).toBe('mission')
    expect(calls()).toHaveLength(1)
  })
  it('fails closed when the local profile is not ready', () => {
    localStorage.removeItem('userId')
    expect(() => createMissionLaunchAttempt()).toThrow('本机身份尚未就绪')
    expect(sessionStorage.length).toBe(0)
  })
})
