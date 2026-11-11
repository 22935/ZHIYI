import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentosApi } from '@/services/api/agentos'
import MarketplaceToolDialog from './MarketplaceToolDialog.vue'

describe('managed document tool', () => {
  afterEach(() => vi.restoreAllMocks())
  it('uploads a file and submits its opaque workspace path to the backend', async () => {
    vi.spyOn(agentosApi, 'uploadMarketplaceToolFile').mockResolvedValue({ sourcePath: 'inputs/opaque.pdf', sizeBytes: 4 })
    const execute = vi.spyOn(agentosApi, 'executeMarketplaceTool').mockResolvedValue({ text: '实际提取的文字' })
    const wrapper = mount(MarketplaceToolDialog, { props: { job: { jobId: 'job-1', catalogId: 'tool.pdf-parser', status: 'running', ownerScope: 't', displayName: 'PDF 解析', createdAt: '', updatedAt: '' } }, global: { stubs: { 'el-dialog': { template: '<section><slot /></section>' } } } })
    const input = wrapper.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [new File(['test'], 'source.pdf')] })
    await input.trigger('change')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(execute).toHaveBeenCalledWith('job-1', { sourcePath: 'inputs/opaque.pdf', firstPage: 1 })
    expect(wrapper.text()).toContain('实际提取的文字')
    expect(wrapper.find('[role=alert]').exists()).toBe(false)
  })

  it('explains OCR limitations as a real tool failure', async () => {
    vi.spyOn(agentosApi, 'uploadMarketplaceToolFile').mockResolvedValue({ sourcePath: 'inputs/scan.pdf', sizeBytes: 4 })
    vi.spyOn(agentosApi, 'executeMarketplaceTool').mockResolvedValue({ error: 'OCR_NOT_AVAILABLE' })
    const wrapper = mount(MarketplaceToolDialog, { props: { job: { jobId: 'job-1', catalogId: 'tool.pdf-parser', status: 'running', ownerScope: 't', displayName: 'PDF 解析', createdAt: '', updatedAt: '' } }, global: { stubs: { 'el-dialog': { template: '<section><slot /></section>' } } } })
    const input = wrapper.get('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [new File(['test'], 'scan.pdf')] })
    await input.trigger('change')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toContain('暂不支持 OCR')
    expect(wrapper.find('pre').exists()).toBe(false)
  })
})
