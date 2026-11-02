import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MissionRevisionNotice from './MissionRevisionNotice.vue'
import { agentosApi } from '@/services/api/agentos'
import { capabilitiesFixture } from '@/test/fixtures/runCapabilities'
vi.mock('@/services/api/agentos', () => ({ agentosApi: { getRunRevision: vi.fn(), decideRunRevision: vi.fn(), applyRunRevision: vi.fn() } }))
const observation = (extra = {}) => ({ missionId: 'm', runId: 'r', sourceRevision: 1, targetRevision: 2,
  status: 'REVISION_CHANGED' as const, runStatus: 'running', impact: 'NOT_ANALYZED' as const, decisions: [], ...extra })
const props = { missionId: 'm', runId: 'r', revision: 2, runStatus: 'running',
  actionCapabilities: capabilitiesFixture('r', 'm', 'running', 1, { canDecideRevision: true }) }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(agentosApi.getRunRevision).mockResolvedValue(observation())
})
describe('MissionRevisionNotice', () => {
  it('keeps historical or identity-uncertain revision decisions read-only', async () => {
    const wrapper = mount(MissionRevisionNotice, { props: { ...props, readonly: true } })
    await flushPromises()
    expect(wrapper.findAll('button')[0].attributes('disabled')).toBeDefined()
    await (wrapper.vm as any).decide('CONTINUE')
    await (wrapper.vm as any).apply()
    expect(agentosApi.decideRunRevision).not.toHaveBeenCalled()
    expect(agentosApi.applyRunRevision).not.toHaveBeenCalled()
    wrapper.unmount()
  })
  it('shows an explicit difference and retries exactly the same scoped decision', async () => {
    vi.mocked(agentosApi.decideRunRevision).mockRejectedValueOnce(new Error('lost response')).mockResolvedValueOnce({} as any)
    const wrapper = mount(MissionRevisionNotice, { props })
    await flushPromises()
    expect(wrapper.text()).toContain('尚未分析任务影响')
    await wrapper.findAll('button')[0].trigger('click'); await flushPromises()
    const first = vi.mocked(agentosApi.decideRunRevision).mock.calls[0]
    expect(first.slice(0, 2)).toEqual(['m', 'r'])
    expect(first[2]).toMatchObject({ decision: 'CONTINUE', sourceRevision: 1, targetRevision: 2 })
    await wrapper.findAll('button')[0].trigger('click'); await flushPromises()
    expect(vi.mocked(agentosApi.decideRunRevision).mock.calls[1]).toEqual(first)
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })
  it('restores a requested decision and applies only after cancellation', async () => {
    const receipt = { ...observation(), operationId: 'saved-op', decision: 'REQUEST_REPLAN', actorId: 'u', tenantId: 't', createdAt: 'now' }
    vi.mocked(agentosApi.getRunRevision).mockResolvedValue(observation({ decisions: [receipt] }) as any)
    const wrapper = mount(MissionRevisionNotice, { props })
    await flushPromises()
    expect(wrapper.text()).toContain('请先通过 Run 的取消入口')
    expect(wrapper.findAll('button').some(b => b.text() === '按已选版本新建 Run')).toBe(false)
    vi.mocked(agentosApi.getRunRevision).mockResolvedValue(observation({ runStatus: 'cancelled', decisions: [receipt] }) as any)
    await wrapper.setProps({ runStatus: 'cancelled', actionCapabilities: capabilitiesFixture('r', 'm', 'cancelled', 2, { canApplyRevision: true }) }); await flushPromises()
    vi.mocked(agentosApi.applyRunRevision).mockResolvedValue({ status: 'SUCCESSOR_CREATED', runId: 'successor' })
    await wrapper.find('button').trigger('click'); await flushPromises()
    expect(agentosApi.applyRunRevision).toHaveBeenCalledWith('m', 'r', 'saved-op')
  })
  it('hides current differences and terminal decisions', async () => {
    vi.mocked(agentosApi.getRunRevision).mockResolvedValue(observation({ status: 'CURRENT' }) as any)
    const wrapper = mount(MissionRevisionNotice, { props }); await flushPromises()
    expect(wrapper.find('section').exists()).toBe(false)
    vi.mocked(agentosApi.getRunRevision).mockResolvedValue(observation({ runStatus: 'completed' }))
    await wrapper.setProps({ runId: 'completed' }); await flushPromises()
    expect(wrapper.findAll('button')).toHaveLength(0)
  })
  it('requires refreshing a revision conflict', async () => {
    vi.mocked(agentosApi.decideRunRevision).mockRejectedValue({ response: { status: 409 } })
    const wrapper = mount(MissionRevisionNotice, { props }); await flushPromises()
    await wrapper.findAll('button')[1].trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('决定已过期或冲突')
  })
  it('ignores a slow observation for the previous Run', async () => {
    let resolve: (value: any) => void = () => {}
    vi.mocked(agentosApi.getRunRevision).mockReturnValueOnce(new Promise(r => { resolve = r }))
    const wrapper = mount(MissionRevisionNotice, { props })
    vi.mocked(agentosApi.getRunRevision).mockResolvedValue(observation({ runId: 'new', status: 'CURRENT' }) as any)
    await wrapper.setProps({ runId: 'new' }); await flushPromises()
    resolve(observation()); await flushPromises()
    expect(wrapper.find('section').exists()).toBe(false)
  })
})
