import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h, KeepAlive, nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { GraphProjection } from '@/services/api/agentos'
import AcgTopologyGraph from './AcgTopologyGraph.vue'


const { networks, flowCalls } = vi.hoisted(() => ({
  networks: [] as any[],
  flowCalls: { actualSize: vi.fn(), overview: vi.fn(), zoomBy: vi.fn() }
}))
vi.mock('./AcgExecutionFlow.vue', async () => {
  const { defineComponent, h } = await import('vue')
  return { default: defineComponent({
    props: ['blueprint', 'selectedId', 'anchorId', 'statuses', 'positions'],
    emits: ['select', 'doubleClick', 'zoom'],
    setup(props, { emit, slots, expose }) {
      expose({ ...flowCalls, close: () => emit('select', '') })
      return () => h('div', { class: 'mock-execution-flow' }, [
        ...props.blueprint.nodes.map((node: any) => h('button', {
          'data-node': node.nodeId,
          onClick: () => emit('select', props.selectedId === node.nodeId ? '' : node.nodeId)
        }, `${node.name} ${props.statuses[node.nodeId].label}`)),
        props.selectedId ? slots.detail?.() : null
      ])
    }
  }) }
})
vi.mock('vis-network', () => ({ Network: vi.fn(function (_element, data, options) {
  const instance = { data, options, on: vi.fn(), once: vi.fn(), destroy: vi.fn(), setOptions: vi.fn(),
    selectNodes: vi.fn(), unselectAll: vi.fn(), redraw: vi.fn(), fit: vi.fn(), moveTo: vi.fn(),
    getScale: () => 1, getViewPosition: () => ({ x: 0, y: 0 }) }
  networks.push(instance)
  return instance
}) }))
vi.mock('@/services/api/workflow', () => ({ workflowApi: { listRunResourceCalls: vi.fn(async () => ({
  items: [{ callId: 'c1', stepId: 'n3', model: 'glm-4', usage: {
    inputTokens: 100, outputTokens: 50, cacheReadTokens: 40, totalTokens: 150
  } }], nextCursor: null, total: 1
})) } }))
const blueprint: GraphProjection = {
  graphId: 'execution-preview',
  nodes: [1, 2, 3, 4, 5].map(i => ({ nodeId: `n${i}`, nodeType: 'step', name: `Task ${i}` })),
  edges: [1, 2, 3, 4].map(i => ({ edgeId: `e${i}`, sourceId: `n${i}`, targetId: `n${i + 1}`, edgeType: 'dependency' }))
}
const wrappers: ReturnType<typeof mount>[] = []
const failedStepStates = [{ stepId: 'n3', status: 'failed', agentName: 'worker', attempt: 1, retryCount: 0 }]
const setup = async (extra = {}) => {
  const wrapper = mount(AcgTopologyGraph, {
    props: { blueprint, workbench: true, observeResize: true, runtimePhases: { n3: 'running' }, ...extra },
    global: { stubs: { ElIcon: { template: '<span><slot /></span>' } } }
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
const click = async (wrapper: ReturnType<typeof mount>, label: string) => {
  await wrapper.findAll('button').find(button => button.text() === label)!.trigger('click')
  await flushPromises()
  await vi.advanceTimersByTimeAsync(150)
}
const ids = (wrapper: ReturnType<typeof mount>) => wrapper.findAll('[data-node]').map(node => node.attributes('data-node'))
beforeEach(() => { vi.useFakeTimers(); networks.length = 0; vi.clearAllMocks() })
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()); vi.useRealTimers() })

describe('execution flow integration', () => {
  it('retains the topology renderer and camera when its Workbench is cached', async () => {
    const visible = ref(true)
    const phases = ref<Record<string, string>>({})
    const host = defineComponent({ setup: () => () => h(KeepAlive, null, { default: () => visible.value
      ? h(AcgTopologyGraph, { blueprint, workbench: true, observeResize: true, runtimePhases: phases.value, stepStates: failedStepStates }) : null }) })
    const wrapper = mount(host, { global: { stubs: { ElIcon: true } } }); wrappers.push(wrapper)
    await flushPromises()
    await click(wrapper, '异常路径')
    const uid = wrapper.findComponent(AcgTopologyGraph).vm.$.uid
    const network = networks[0]
    network.getScale = () => 1.7; network.getViewPosition = () => ({ x: 80, y: 120 })
    network.moveTo.mockClear()
    visible.value = false; await nextTick()
    phases.value.n3 = 'running'
    await vi.advanceTimersByTimeAsync(150)
    visible.value = true; await nextTick(); await flushPromises()
    expect(wrapper.findComponent(AcgTopologyGraph).vm.$.uid).toBe(uid)
    expect(networks).toHaveLength(1); expect(network.destroy).not.toHaveBeenCalled()
    expect(network.getScale()).toBe(1.7); expect(network.getViewPosition()).toEqual({ x: 80, y: 120 })
    expect(network.moveTo).not.toHaveBeenCalled()
  })
  it('renders the running neighborhood with Vue Flow without creating a canvas network', async () => {
    const wrapper = await setup()
    await vi.advanceTimersByTimeAsync(150)
    expect(ids(wrapper)).toEqual(['n2', 'n3', 'n4'])
    expect(wrapper.get('[data-node="n3"]').text()).toContain('\u8fd0\u884c\u4e2d')
    expect(networks).toHaveLength(0)
  })
  it('routes overview and actual-size controls to the execution flow', async () => {
    const wrapper = await setup()
    await click(wrapper, '\u5168\u90e8\u6b65\u9aa4')
    expect(ids(wrapper)).toHaveLength(5)
    await wrapper.get('.graph-fab__ball').trigger('click')
    await click(wrapper, '\u5168\u56fe\u603b\u89c8')
    expect(flowCalls.overview).toHaveBeenCalled()
    await click(wrapper, '\u5b9e\u9645\u5927\u5c0f')
    expect(flowCalls.actualSize).toHaveBeenCalledWith('n3', 240)
    await click(wrapper, '\u5b9a\u4f4d\u4efb\u52a1')
    expect(ids(wrapper)).toEqual(['n2', 'n3', 'n4'])
  })
  it('updates runtime statuses without resetting the viewport', async () => {
    const wrapper = await setup()
    await wrapper.setProps({ runtimePhases: { n2: 'completed', n3: 'running' } })
    expect(wrapper.get('[data-node="n2"]').text()).toContain('\u5df2\u5b8c\u6210')
    expect(flowCalls.actualSize).not.toHaveBeenCalled()
  })
  it('follows an external selection outside the current neighborhood', async () => {
    const wrapper = await setup()
    await wrapper.setProps({ focusNodeId: 'n5' })
    await flushPromises()
    expect(ids(wrapper)).toEqual(['n4', 'n5'])
    expect(flowCalls.actualSize).toHaveBeenCalledWith('n5')
    expect(wrapper.emitted('nodeSelected')).toContainEqual(['n5'])
  })
  it('puts token usage and dependency navigation inside the expanded node', async () => {
    const wrapper = await setup({ runId: 'run-flow' })
    await wrapper.get('[data-node="n3"]').trigger('click')
    await flushPromises()
    const card = wrapper.get('.mock-execution-flow .uml-card')
    expect(card.text()).toContain('glm-4')
    expect(card.text()).toContain('150')
    expect(card.text()).toContain('60')
    expect(card.text()).toContain('40')
    expect(wrapper.find('.node-detail').exists()).toBe(false)
    await card.get('.uml-card__dep-group button').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('nodeSelected')).toContainEqual(['n2'])
    await wrapper.get('[aria-label="\u6536\u8d77\u8282\u70b9\u8be6\u60c5"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('.uml-card').exists()).toBe(false)
  })
  it('keeps the abnormal-path view on the existing network renderer', async () => {
    const wrapper = await setup({ stepStates: failedStepStates })
    await click(wrapper, '\u5f02\u5e38\u8def\u5f84')
    expect(wrapper.find('.mock-execution-flow').exists()).toBe(false)
    expect(networks).toHaveLength(1)
    expect(networks[0].data.nodes.getIds()).toEqual(['n2', 'n3', 'n4'])
    expect(networks[0].options.physics.enabled).toBe(true)
  })
  it('shows the empty hint when no abnormal steps exist', async () => {
    const wrapper = await setup()
    await click(wrapper, '\u5f02\u5e38\u8def\u5f84')
    expect(wrapper.text()).toContain('\u5f53\u524d\u8fd0\u884c\u6ca1\u6709\u5f02\u5e38\u8def\u5f84')
  })
  it('can close full execution details after expanding a node', async () => {
    const wrapper = await setup({ stepStates: [{ stepId: 'n3', status: 'running', agentName: 'worker', attempt: 1, retryCount: 0 }] })
    await wrapper.get('[data-node="n3"]').trigger('click')
    await wrapper.get('.uml-card__more').trigger('click')
    expect(wrapper.find('.node-detail').exists()).toBe(true)
    await wrapper.get('.node-detail > header button').trigger('click')
    expect(wrapper.find('.node-detail').exists()).toBe(false)
    expect(wrapper.find('.uml-card').exists()).toBe(false)
  })
})
