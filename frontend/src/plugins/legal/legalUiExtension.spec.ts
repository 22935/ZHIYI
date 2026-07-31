import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import LegalTaskExtension from './LegalTaskExtension.vue'
import LegalStrategyPanel from './LegalStrategyPanel.vue'

const modelValue = {
  contractText: '', reviewGoal: '识别风险', contractType: '', useTemplateWorkflow: false,
  evidenceFirst: true, riskParallel: true, conservativeReview: true
}

describe('Legal UI extension', () => {
  it('owns legal task wording outside the generic workbench', () => {
    const wrapper = mount(LegalTaskExtension, {
      props: { modelValue },
      global: { stubs: { 'el-input': true, 'el-tag': true } }
    })
    expect(wrapper.text()).toContain('法律任务扩展')
    expect(wrapper.text()).toContain('合同文本')
    expect(wrapper.text()).toContain('合同审查目标')
  })

  it('renders only backend-supported legal strategy fields', () => {
    const wrapper = mount(LegalStrategyPanel, {
      props: { modelValue },
      global: { stubs: { 'el-checkbox': { template: '<label><slot /></label>' } } }
    })
    expect(wrapper.text()).toContain('Evidence 优先')
    expect(wrapper.text()).toContain('风险并行分析')
    expect(wrapper.text()).toContain('保守人工审核')
    expect(wrapper.text()).toContain('固定合同审查 Workflow')
  })
})
