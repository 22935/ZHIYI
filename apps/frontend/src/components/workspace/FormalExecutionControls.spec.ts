import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { reactive } from 'vue'
import { webcrypto } from 'node:crypto'
import { agentosApi, type WorkflowRun } from '@/services/api/agentos'
import { nextFormalAction, prepareFormalCommand } from '@/features/acg/formalControl'
import FormalExecutionControls from './FormalExecutionControls.vue'
import { capabilitiesFixture } from '@/test/fixtures/runCapabilities'

const permitted = (): WorkflowRun => ({
  runId: 'run', missionId: 'mission', workflowId: 'workflow', domain: 'test', status: 'pending', steps: [], runtimeRevision: 7,
  formalControl: { status: 'ACTIVATED', executionAuthorized: true, permitIssued: true, dispatchEligible: true, dispatchEnabled: true,
    commitId: 'commit', commitmentRevision: 1, materializationId: 'mat', activationId: 'activation', graphId: 'graph', graphVersion: 1,
    handoffId: 'handoff', handoffStatus: 'STATE_PREPARED', permitId: 'permit', permitStatus: 'ISSUED', dispatch: null }
})
const render = (run: WorkflowRun | null = permitted(), extra = {}) => {
  if (run && run.actionCapabilities === undefined) run.actionCapabilities = capabilitiesFixture(run.runId, run.missionId, run.status, run.runtimeRevision || 0,
    { canReview: run.status === 'waiting_review', canExecuteFormalAction: Boolean(nextFormalAction(run)), formalActions: nextFormalAction(run) ? [nextFormalAction(run)!] : [] })
  return mount(FormalExecutionControls, {
  props: { run, missionId: 'mission', runId: 'run', historical: false, canCancel: true, cancelPending: false, ...extra },
  global: { stubs: { WorkflowReviewPanel: { template: '<button @click="$emit(\'reviewed\')">通过审核</button>' } } }
  })
}
const execute = (wrapper: ReturnType<typeof render>) => wrapper.findAll('button').find(b => /执行任务|重试原操作/.test(b.text()))!
beforeEach(() => { localStorage.clear(); vi.restoreAllMocks(); vi.stubGlobal('crypto', webcrypto) })

describe('formal Workbench controls', () => {
  it('keeps embedded controls read-only and exposes technical evidence on demand', async () => {
    const post = vi.spyOn(agentosApi, 'submitFormalControl')
    const w = render(permitted(), {embedded:true,readonly:true})
    expect(w.text()).toContain('任务进展')
    expect(w.get('details').attributes('open')).toBeUndefined()
    expect(w.get('summary').text()).toBe('运行状态与授权引用')
    await execute(w).trigger('click')
    await w.findAll('button').find(b => b.text() === '取消任务')!.trigger('click')
    expect(post).not.toHaveBeenCalled()
    expect(w.emitted('cancel')).toBeUndefined()
    w.unmount()
  })
  it('never dispatches on Permit issuance or on refresh', async () => {
    const post = vi.spyOn(agentosApi, 'submitFormalControl')
    const w = render()
    expect(w.text()).toContain('许可已签发，尚未执行')
    await w.get('header button').trigger('click')
    expect(w.emitted('refresh')).toHaveLength(1)
    expect(post).not.toHaveBeenCalled()
    w.unmount()
  })
  it('double click submits once, ACK does not invent a running state', async () => {
    let finish!: (v: { operationId: string; status: string }) => void
    const post = vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const w = render()
    const button = w.get('.formal-control__primary')
    await button.trigger('click'); await button.trigger('click')
    expect(post).toHaveBeenCalledTimes(1)
    finish({ operationId: post.mock.calls[0][3].operationId, status: 'ACCEPTED', dispatchId: 'dispatch' } as any); await flushPromises()
    expect(w.text()).toContain('pending')
    expect(w.emitted('succeeded')?.[0]?.[0]).toMatchObject({ action: 'dispatch', status: 'ACCEPTED', dispatchId: 'dispatch' })
    expect(execute(w).attributes('disabled')).toBeDefined()
    expect(Object.keys(post.mock.calls[0][3]).sort()).toEqual(['operationId', 'expectedPermitId', 'expectedGraphId', 'expectedGraphVersion', 'expectedRuntimeRevision'].sort())
    w.unmount()
  })
  it('lost ACK retries the same operation and comparison revision across remount', async () => {
    const post = vi.spyOn(agentosApi, 'submitFormalControl').mockRejectedValue(new Error('ACK lost'))
    const w = render(); await execute(w).trigger('click'); await flushPromises()
    const original = post.mock.calls[0][3]
    w.unmount()
    const run = permitted(); run.runtimeRevision = 8
    const reopened = render(run); await execute(reopened).trigger('click'); await flushPromises()
    expect(post.mock.calls[1][3]).toEqual(original)
    expect(post.mock.calls[1][3]).toHaveProperty('expectedRuntimeRevision', 7)
    expect(reopened.emitted('succeeded')).toBeUndefined()
    reopened.unmount()
  })
  it('reopens an accepted Dispatch from the Run query without another POST', () => {
    const run = permitted()
    run.formalControl!.dispatch = { dispatchId: 'dispatch', runId: 'run', permitId: 'permit', graphVersion: 1, status: 'ACCEPTED' }
    const post = vi.spyOn(agentosApi, 'submitFormalControl')
    const w = render(run)
    expect(w.text()).toContain('已持久接受')
    expect(execute(w)).toBeUndefined()
    expect(post).not.toHaveBeenCalled()
    w.unmount()
  })
  it.each([403, 409, 422])('disables dangerous actions after rejection %s', async status => {
    vi.spyOn(agentosApi, 'submitFormalControl').mockRejectedValue({ response: { status } })
    const w = render(); await execute(w).trigger('click'); await flushPromises()
    expect(execute(w).attributes('disabled')).toBeDefined()
    expect(w.text()).toContain('控制已禁用')
    expect(w.emitted('succeeded')).toBeUndefined()
    w.unmount()
  })
  it('fails closed on unavailable Run, historical state and corrupt operation cache', async () => {
    const w = render()
    await w.setProps({ run: null })
    expect(w.text()).toContain('无法验证正式状态')
    expect(execute(w)).toBeUndefined()
    const restored = permitted()
    restored.actionCapabilities = capabilitiesFixture('run', 'mission', 'pending', 7,
      { canExecuteFormalAction: true, formalActions: ['dispatch'] })
    await w.setProps({ run: restored, historical: true })
    expect(execute(w).attributes('disabled')).toBeDefined()
    await w.setProps({ historical: false })
    prepareFormalCommand(permitted(), 'dispatch', localStorage)
    const key = localStorage.key(0)!; localStorage.setItem(key, '{broken')
    const post = vi.spyOn(agentosApi, 'submitFormalControl')
    await execute(w).trigger('click'); await flushPromises()
    expect(w.text()).toContain('重试记录不可用或已损坏')
    expect(post).not.toHaveBeenCalled()
    w.unmount()
  })
  it('uses existing review/cancel handlers and shows failure evidence read-only', async () => {
    const run = permitted(); run.status = 'waiting_review'
    const w = render(run)
    await w.findAll('button').find(b => b.text() === '通过审核')!.trigger('click')
    expect(w.emitted('refresh')).toHaveLength(1)
    await w.findAll('button').find(b => b.text() === '取消任务')!.trigger('click')
    expect(w.emitted('cancel')).toHaveLength(1)
    await w.setProps({ run: { ...run, status: 'failed', failureCode: 'DISPATCH_RECOVERY_BLOCKED', lifecycleMessage: '需要核对副作用证据' } })
    expect(w.text()).toContain('DISPATCH_RECOVERY_BLOCKED')
    expect(w.text()).toContain('需要核对副作用证据')
    expect(execute(w)).toBeUndefined()
    w.unmount()
  })
  it('leaves Legacy controls absent and unknown formal states read-only', () => {
    const run = permitted(); delete run.formalControl
    run.actionCapabilities = null
    const legacy = render(run); expect(legacy.find('section').exists()).toBe(false); legacy.unmount()
    const unknown = permitted(); unknown.formalControl!.status = 'UNRECOGNIZED'
    expect(nextFormalAction(unknown)).toBeNull()
    unknown.formalControl!.status = 'ACTIVATED'; unknown.formalControl!.dispatchEnabled = false
    expect(nextFormalAction(unknown)).toBeNull()
  })
  it('shows an explicitly authorized Cancel without C2 evidence and keeps execution consent separate', async () => {
    const run = permitted(); delete run.formalControl
    const wrapper = render(run, { executionReadonly: true })
    expect(wrapper.find('.formal-control__primary').exists()).toBe(false)
    expect(wrapper.text()).toContain('Runtime 已确认此 Run 可停止')
    const cancel = wrapper.findAll('button').find(button => button.text() === '取消任务')!
    expect(cancel.attributes('disabled')).toBeUndefined()
    await cancel.trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
    wrapper.unmount()
  })
  it('offers one explicit action at each formally observed stage', () => {
    const run = permitted(); const c = run.formalControl!
    c.status = 'PLANNING_ACCEPTED'; run.status = 'planning'; expect(nextFormalAction(run)).toBe('materialize')
    c.status = 'MATERIALIZED_INACTIVE'; expect(nextFormalAction(run)).toBe('activate')
    c.status = 'ACTIVATED_PAUSED'; c.handoffId = null; expect(nextFormalAction(run)).toBe('handoff')
    c.handoffId = 'handoff'; c.permitIssued = false; expect(nextFormalAction(run)).toBe('permit')
    c.status = 'ACTIVATED'; c.permitIssued = true; expect(nextFormalAction(run)).toBe('dispatch')
    c.graphVersion = 0; expect(nextFormalAction(run)).toBeNull()
  })
  it('confirms replay with the same operation and never advances another command', async () => {
    const post = vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(async (_m, _r, _a, command) =>
      ({ operationId: command.operationId, status: 'IDEMPOTENT_REPLAY', dispatchId: 'original' }))
    const w = render(); await execute(w).trigger('click'); await flushPromises()
    expect(w.emitted('succeeded')?.[0]?.[0]).toMatchObject({ status: 'IDEMPOTENT_REPLAY', dispatchId: 'original' })
    await execute(w).trigger('click'); expect(post).toHaveBeenCalledTimes(1); w.unmount()
  })
  it.each(['wrong-operation', 'missing-dispatch', 'unconfirmed'])('rejects malformed receipt %s', async kind => {
    vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(async (_m, _r, _a, command) => ({
      operationId: kind === 'wrong-operation' ? 'other' : command.operationId,
      status: kind === 'unconfirmed' ? 'RUNNING' : 'ACCEPTED', dispatchId: kind === 'missing-dispatch' ? undefined : 'dispatch' }))
    const w = render(); await execute(w).trigger('click'); await flushPromises()
    expect(w.emitted('succeeded')).toBeUndefined(); w.unmount()
  })
  it('ignores the previous Run response after selection changes', async () => {
    let finish!: (value: any) => void
    const post = vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const w = render(); await execute(w).trigger('click')
    await w.setProps({ runId: 'other', run: { ...permitted(), runId: 'other' } })
    finish({ operationId: post.mock.calls[0][3].operationId, status: 'ACCEPTED', dispatchId: 'late' })
    await flushPromises(); expect(w.emitted('succeeded')).toBeUndefined(); w.unmount()
  })
  it.each(['graphId', 'graphVersion', 'permitId', 'runtimeRevision', 'status', 'capability'])('rejects a stale same-Run receipt after %s changes', async field => {
    let finish!: (value: any) => void
    const post = vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const w = render(); await execute(w).trigger('click')
    const changed = permitted()
    if (field === 'runtimeRevision') changed.runtimeRevision = 8
    else if (field === 'status') changed.status = 'running'
    else if (field === 'capability') changed.actionCapabilities = null
    else (changed.formalControl as any)[field] = field === 'graphVersion' ? 2 : 'changed'
    await w.setProps({ run: changed })
    finish({ operationId: post.mock.calls[0][3].operationId, status: 'ACCEPTED', dispatchId: 'late' })
    await flushPromises(); expect(w.emitted('succeeded')).toBeUndefined(); w.unmount()
  })

  it.each(['runId', 'missionId'] as const)('invalidates a late receipt when the same Run object changes %s', async field => {
    let finish!: (value: any) => void
    const post = vi.spyOn(agentosApi, 'submitFormalControl').mockImplementation(() => new Promise(resolve => { finish = resolve }))
    const run = reactive(permitted())
    const w = render(run); await execute(w).trigger('click')
    if (field === 'runId') run.runId = 'replacement-run'
    else run.missionId = 'replacement-mission'
    await flushPromises()
    finish({ operationId: post.mock.calls[0][3].operationId, status: 'ACCEPTED', dispatchId: 'late' })
    await flushPromises()
    expect(w.emitted('succeeded')).toBeUndefined()
    w.unmount()
  })

})
