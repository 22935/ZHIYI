import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { agentosApi, type RuntimeResourceItem } from '@/services/api/agentos'
import ResourceOverviewPanel from './ResourceOverviewPanel.vue'
import ResourceDetailPanel from './ResourceDetailPanel.vue'
import ResourceRegistrationDialog from './ResourceRegistrationDialog.vue'

beforeEach(() => {
  vi.spyOn(agentosApi, 'listResourceUsage').mockResolvedValue({ resourceId: 'fixture', items: [], total: 0 })
  vi.spyOn(agentosApi, 'getResourceHealthHistory').mockResolvedValue({ resourceId: 'fixture', items: [], total: 0 })
  vi.spyOn(agentosApi, 'getResourceCredential').mockResolvedValue({ resourceId: 'fixture', credentialId: 'credential-fixture', createdAt: '2026-01-01T00:00:00Z' })
})
afterEach(() => vi.restoreAllMocks())
const item = (id: string, placement: string): RuntimeResourceItem => ({
  profile: { resourceId: id, resourceType: 'worker', runtimeKind: 'execution_backend', nodeId: 'node-1',
    deploymentTier: placement, capabilities: ['exec.agents'], domains: [], enabled: true, capacity: 2, version: 1,
    computeCapacity: { cpuCores: 0, memoryMb: 0, gpuMemoryMb: 0 } },
  snapshot: { healthStatus: 'unknown' }, snapshotVersion: 1
})
const stubs = { 'el-icon': true, 'el-drawer': true }

describe('resource plane adaptation', () => {
  it('renders device and unknown placements without dropping rows or inventing compute', async () => {
    vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [item('embedded', 'device'), item('future', 'satellite')], total: 2 })
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [], total: 0 })
    const wrapper = mount(ResourceOverviewPanel, { global: { stubs } })
    await flushPromises()
    expect(wrapper.findAll('.resource-row')).toHaveLength(2)
    expect(wrapper.text()).toContain('本机设备')
    expect(wrapper.text()).toContain('其他位置 · satellite')
    // 摘要卡已移除：算力改为按行展示，零容量不得虚报成「0核」。
    expect(wrapper.text()).not.toContain('0核')
    expect(wrapper.findAll('.resource-row__capacity').length).toBe(2)
    wrapper.unmount()
  })

  it('shows per-runtime compute on rows without double counting a shared node', async () => {
    const a = item('a', 'device'); a.profile.computeCapacity = { cpuCores: 8, memoryMb: 16384 }
    const b = item('b', 'device'); b.profile.computeCapacity = { cpuCores: 8, memoryMb: 16384 }
    vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [a, b], total: 2 })
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [], total: 0 })
    const wrapper = mount(ResourceOverviewPanel, { global: { stubs } })
    await flushPromises()
    // 同一节点上的两个运行时各自展示自身容量，不再把节点算力聚合成 16核。
    expect(wrapper.findAll('.resource-row__capacity').every(cell => cell.text().includes('8核'))).toBe(true)
    expect(wrapper.text()).not.toContain('16核')
    wrapper.unmount()
  })

  it('keeps resource rows when the node catalog is unavailable', async () => {
    vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [item('a', 'device')], total: 1 })
    vi.spyOn(agentosApi, 'listNodes').mockRejectedValue(new Error('offline'))
    const wrapper = mount(ResourceOverviewPanel, { global: { stubs } })
    await flushPromises()
    expect(wrapper.findAll('.resource-row')).toHaveLength(1)
    expect(wrapper.text()).toContain('服务目录仍可单独查看')
    wrapper.unmount()
  })

  it('groups resources by customer deployment and surfaces an offline connection action', async () => {
    const local = item('local', 'local'); local.snapshot.healthStatus = 'online'
    const edge = item('edge', 'edge'); edge.snapshot.healthStatus = 'offline'
    const cloud = item('cloud', 'cloud'); cloud.snapshot.healthStatus = 'online'
    vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [local, edge, cloud], total: 3 })
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [], total: 0 })
    const wrapper = mount(ResourceOverviewPanel, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('我的设备')
    expect(wrapper.text()).toContain('边缘节点')
    expect(wrapper.text()).toContain('云端服务')
    expect(wrapper.text()).toContain('检测连接')
    wrapper.unmount()
  })

  it('filters catalog items by customer resource type and health', async () => {
    const model = item('model', 'cloud'); model.profile.runtimeKind = 'model_server'
    const offlineTool = item('tool', 'edge'); offlineTool.profile.runtimeKind = 'tool_service'; offlineTool.snapshot.healthStatus = 'offline'
    vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [model, offlineTool], total: 2 })
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [], total: 0 })
    const wrapper = mount(ResourceOverviewPanel, { global: { stubs } })
    await flushPromises()
    const selects = wrapper.findAll('.resource-catalog-filters select')
    await selects[0].setValue('tool')
    await selects[2].setValue('offline')
    expect(wrapper.findAll('.resource-row')).toHaveLength(1)
    expect(wrapper.find('.resource-row').text()).toContain('tool')
    wrapper.unmount()
  })

  it('filters heterogeneous resources by provider and source and displays their provenance', async () => {
    const vendor = item('vendor-runtime', 'edge')
    vendor.profile.provider = 'Acme'
    vendor.profile.sourceType = 'kubernetes'
    vendor.profile.adapter = 'k8s-agentos'
    const other = item('other-runtime', 'cloud')
    other.profile.provider = 'Other'
    other.profile.sourceType = 'openai-compatible'
    vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [vendor, other], total: 2 })
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [], total: 0 })
    const wrapper = mount(ResourceOverviewPanel, { global: { stubs } })
    await flushPromises()
    const selects = wrapper.findAll('.resource-catalog-filters select')
    await selects[4].setValue('kubernetes')
    expect(wrapper.findAll('.resource-row')).toHaveLength(1)
    expect(wrapper.find('.resource-row__meta').text()).toContain('Acme')
    expect(wrapper.find('.resource-row__meta').text()).toContain('kubernetes')
    const providerFilter = wrapper.findAll('.resource-catalog-filters select')[5]
    await providerFilter.setValue('Other')
    expect(wrapper.findAll('.resource-row')).toHaveLength(0)
    wrapper.unmount()
  })

  it('shows registered nodes before they have a runtime attached', async () => {
    vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [], total: 0 })
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [{ profile: { nodeId: 'node:new', displayName: '新设备', placement: 'edge', trust: 'trusted', ownerScope: 'customer', enabled: true, computeCapacity: { cpuCores: 4, memoryMb: 8192 } }, healthStatus: 'offline', snapshotVersion: 1 }], total: 1 })
    const wrapper = mount(ResourceOverviewPanel, { global: { stubs } })
    await flushPromises()
    expect(wrapper.find('.resource-topology').text()).toContain('新设备')
    expect(wrapper.find('.resource-topology').text()).toContain('边缘节点')
    expect(wrapper.find('.resource-topology').text()).toContain('4 核 CPU')
    wrapper.unmount()
  })

  it('enables a registered device through the tenant-scoped node command', async () => {
    vi.spyOn(agentosApi, 'listResources').mockResolvedValue({ items: [], total: 0 })
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [{ profile: { nodeId: 'node:paused', displayName: '暂停设备', placement: 'edge', trust: 'trusted', ownerScope: 'customer', enabled: false }, healthStatus: 'offline', snapshotVersion: 1 }], total: 1 })
    const enable = vi.spyOn(agentosApi, 'setNodeEnabled').mockResolvedValue({ nodeId: 'node:paused', enabled: true })
    const wrapper = mount(ResourceOverviewPanel, { global: { stubs } })
    await flushPromises()
    await wrapper.get('.resource-topology__manage').trigger('click')
    await flushPromises()
    expect(enable).toHaveBeenCalledWith('node:paused', true)
    expect(wrapper.get('.resource-topology__manage').text()).toBe('停用设备')
    wrapper.unmount()
  })

  it('does not send runtime commands for a model endpoint', async () => {
    const model = item('endpoint-1', 'cloud'); model.profile.runtimeKind = 'model_endpoint'
    model.profile.provider = 'provider'; model.profile.model = 'model'; model.profile.contextWindowTokens = 8192
    const usage = vi.spyOn(agentosApi, 'listResourceUsage')
    const wrapper = mount(ResourceDetailPanel, { props: { item: model }, global: { stubs: { 'el-icon': true, 'el-switch': true, 'router-link': true } } })
    await flushPromises()
    expect(wrapper.text()).toContain('8192 tokens')
    expect(wrapper.find('el-switch-stub').exists()).toBe(false)
    expect(usage).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('presents resource details before advanced settings', async () => {
    const wrapper = mount(ResourceDetailPanel, { props: { item: item('edge', 'edge') }, global: { stubs: { 'el-icon': true, 'el-switch': true, 'router-link': true } } })
    await flushPromises()
    expect(wrapper.text()).toContain('资源概览')
    expect(wrapper.text()).toContain('高级设置')
    expect(wrapper.text()).toContain('停止后不会删除资源或历史记录')
    wrapper.unmount()
  })

  it('registers a node with the new contract and keeps the one-time secret until acknowledged', async () => {
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [], total: 0 })
    const register = vi.spyOn(agentosApi, 'registerNode').mockResolvedValue({ nodeId: 'node:edge:new', credentialId: 'nc-1', secret: 'one-time-secret', ownerScope: 'scope' })
    const wrapper = mount(ResourceRegistrationDialog, { props: { modelValue: false }, global: { stubs: { 'el-icon': true,
      'el-dialog': { template: '<div><slot name="header" /><slot /><slot name="footer" /></div>' } } } })
    await wrapper.setProps({ modelValue: true }); await flushPromises()
    expect(wrapper.text()).toContain('接入设备')
    expect(wrapper.text()).toContain('端侧设备')
    await wrapper.findAll('input')[0].setValue('node:edge:new')
    await wrapper.findAll('input').find(input => (input.element as HTMLInputElement).placeholder === '该节点所属的操作范围')!.setValue('scope')
    await wrapper.findAll('input').find(input => (input.element as HTMLInputElement).placeholder === '如 kubernetes、vendor_agent')!.setValue('vendor-agent')
    await wrapper.findAll('input').find(input => (input.element as HTMLInputElement).placeholder === '如 NVIDIA、华为、AWS')!.setValue('Acme')
    await wrapper.findAll('input').find(input => (input.element as HTMLInputElement).placeholder === '如 k8s-agentos、vendor-sdk')!.setValue('acme-adapter')
    await wrapper.get('.rr-submit').trigger('click'); await flushPromises()
    expect(register.mock.calls[0][0]).toMatchObject({ profile: { nodeId: 'node:edge:new', placement: 'edge', ownerScope: 'scope', sourceType: 'vendor-agent', provider: 'Acme', adapter: 'acme-adapter' }, snapshot: { nodeId: 'node:edge:new', healthStatus: 'offline' } })
    expect((wrapper.get('textarea').element as HTMLTextAreaElement).value).toBe('one-time-secret')
    expect(wrapper.emitted('registered')).toBeUndefined()
    await wrapper.get('.rr-submit').trigger('click')
    expect(wrapper.emitted('registered')).toHaveLength(1)
    wrapper.unmount()
  })

  it('registers a customer model with its host placement and trust', async () => {
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [{ profile: { nodeId: 'node:edge:1',
      displayName: 'Edge', placement: 'edge', trust: 'sandboxed', ownerScope: 'scope', enabled: true },
      healthStatus: 'offline', snapshotVersion: 1 }], total: 1 })
    const register = vi.spyOn(agentosApi, 'registerResource').mockResolvedValue({ resourceId: 'runtime:1', credentialId: 'rc-1', secret: 'one-time', ownerScope: 'scope' })
    const wrapper = mount(ResourceRegistrationDialog, { props: { modelValue: true }, global: { stubs: {
      'el-icon': true, 'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
      'el-select': { name: 'ElSelect', props: ['modelValue'], template: '<div />' }
    } } })
    await flushPromises()
    await wrapper.findAll('.rr-type')[1].trigger('click'); await flushPromises()
    expect(wrapper.text()).not.toContain('gRPC')
    await wrapper.findAll('input')[0].setValue('runtime:1')
    await wrapper.findAll('select')[0].setValue('node:edge:1')
    wrapper.findAllComponents({ name: 'ElSelect' })[0].vm.$emit('update:modelValue', ['exec.research'])
    await wrapper.findAll('input').find(input => (input.element as HTMLInputElement).placeholder === '如 vLLM、火山引擎')!.setValue('Acme')
    wrapper.findAllComponents({ name: 'ElSelect' })[2].vm.$emit('update:modelValue', ['chat-v1']); await flushPromises()
    await wrapper.findAll('input').find(input => (input.element as HTMLInputElement).placeholder === '例如 https://worker.example.com')!.setValue('https://worker.example.com')
    await wrapper.get('.rr-submit').trigger('click'); await flushPromises()
    expect(register.mock.calls[0][0]).toMatchObject({ profile: { runtimeId: 'runtime:1', nodeId: 'node:edge:1',
      kind: 'model_server', placement: 'edge', trust: 'sandboxed', ownerScope: 'scope',
      provider: 'Acme', adapter: 'agentos_model_http', capabilities: ['exec.research'], modelIds: ['chat-v1'], endpoint: { protocol: 'https', address: 'https://worker.example.com' } },
      snapshot: { runtimeId: 'runtime:1', healthStatus: 'unknown' } })
    expect(register.mock.calls[0][0].profile).not.toHaveProperty('resourceType')
    wrapper.unmount()
  })

  it('registers a customer tool as a tool service runtime', async () => {
    vi.spyOn(agentosApi, 'listNodes').mockResolvedValue({ items: [{ profile: { nodeId: 'node:edge:1',
      displayName: 'Edge', placement: 'edge', trust: 'trusted', ownerScope: 'scope', enabled: true },
      healthStatus: 'offline', snapshotVersion: 1 }], total: 1 })
    const register = vi.spyOn(agentosApi, 'registerResource').mockResolvedValue({ resourceId: 'tool:1', credentialId: 'rc-1', secret: 'one-time', ownerScope: 'scope' })
    const wrapper = mount(ResourceRegistrationDialog, { props: { modelValue: true }, global: { stubs: {
      'el-icon': true, 'el-dialog': { template: '<div><slot /><slot name="footer" /></div>' },
      'el-select': { name: 'ElSelect', props: ['modelValue'], template: '<div />' }
    } } })
    await flushPromises()
    await wrapper.findAll('.rr-type')[2].trigger('click')
    await wrapper.findAll('input')[0].setValue('tool:1')
    await wrapper.findAll('select')[0].setValue('node:edge:1')
    wrapper.findAllComponents({ name: 'ElSelect' })[0].vm.$emit('update:modelValue', ['tool.search'])
    await wrapper.findAll('input').find(input => (input.element as HTMLInputElement).placeholder === '例如 https://worker.example.com')!.setValue('https://tools.example.com')
    await wrapper.get('.rr-submit').trigger('click'); await flushPromises()
    expect(register).toHaveBeenCalledWith(expect.objectContaining({ profile: expect.objectContaining({ kind: 'tool_service', runtimeId: 'tool:1' }) }))
    wrapper.unmount()
  })
})
