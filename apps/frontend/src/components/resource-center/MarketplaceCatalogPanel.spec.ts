import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MarketplaceCatalogPanel from './MarketplaceCatalogPanel.vue'

describe('platform local tool catalog', () => {
  it('shows capabilities, actual formats and dependency requirements', () => {
    const wrapper = mount(MarketplaceCatalogPanel, {
      props: { items: [{ catalogId: 'tool.pdf-parser', kind: 'tool_service', version: '1.0.0', displayName: 'PDF 解析', description: '本地解析', sizeBytes: 4096, category: '文档工具', capabilities: ['pdf.parse'], requirements: { python: '>=3.10', formats: ['pdf → text'], offline: true } }], installations: [], loading: false, busy: false },
      global: { stubs: { 'el-icon': { template: '<span><slot /></span>' } } }
    })
    expect(wrapper.text()).toContain('pdf.parse')
    expect(wrapper.text()).toContain('pdf → text')
    expect(wrapper.text()).toContain('Python >=3.10')
    expect(wrapper.text()).toContain('4.0 KB')
    expect(wrapper.text()).not.toContain('entrypoint')
  })
})
