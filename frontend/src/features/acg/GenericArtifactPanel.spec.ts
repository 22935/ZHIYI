import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import GenericArtifactPanel from './GenericArtifactPanel.vue'


const artifact = {
  artifactId: 'artifact_1',
  type: 'report',
  title: '智能装配生产线实施方案',
  mediaType: 'text/markdown',
  content: '推荐采用模块化柔性装配线。',
  structuredData: {
    title: '智能装配生产线实施方案',
    executiveSummary: '方案满足预算、周期和产能约束。',
    sections: [
      { title: '产能分析', content: '目标节拍需优化至 50 秒。', sourceFields: ['capacity_plan'] },
      { title: '实施计划', content: '项目在 26 周内完成。', sourceFields: ['solution_design'] }
    ],
    calculations: [{
      name: '有效产能', formula: '理论产能 × OEE', result: '244,800 台/年',
      inputs: ['288,000 台', '85%'], assumptions: ['节拍 50 秒']
    }],
    assumptions: ['成本为估算值'],
    openQuestions: ['确认设备供应商报价'],
    sourceRefs: ['src_task_input']
  }
}

describe('GenericArtifactPanel', () => {
  it('presents structured final delivery before audit step outputs', async () => {
    const wrapper = mount(GenericArtifactPanel, {
      props: {
        status: 'completed',
        finalReport: '推荐采用模块化柔性装配线。',
        finalArtifacts: [artifact],
        stepOutputs: [
          { stepId: 'analysis', name: '通用分析', status: 'completed', output: { findings: ['a'] } },
          { stepId: 'deliver', name: '成果生成', status: 'completed', output: { final_answer: 'done' } }
        ]
      }
    })

    expect(wrapper.text()).toContain('最终交付说明')
    expect(wrapper.text()).toContain('智能装配生产线实施方案')
    expect(wrapper.text()).toContain('方案满足预算、周期和产能约束')
    expect(wrapper.findAll('.solution-section')).toHaveLength(2)
    expect(wrapper.find('.delivery-facts').text()).toContain('2方案章节')
    expect(wrapper.find('.step-output-section').text()).toContain('过程产出')
    expect(wrapper.findAll('details')).toHaveLength(2)

    await wrapper.findAll('.delivery-tabs button')[1].trigger('click')
    expect(wrapper.find('.calculation-card').text()).toContain('244,800 台/年')

    await wrapper.findAll('.delivery-tabs button')[2].trigger('click')
    expect(wrapper.find('.decision-grid').text()).toContain('确认设备供应商报价')
  })

  it('falls back to a plain final report when structured data is unavailable', () => {
    const wrapper = mount(GenericArtifactPanel, {
      props: {
        status: 'completed',
        finalReport: '# Final delivery\n\nComplete result.',
        finalArtifacts: [],
        stepOutputs: []
      }
    })

    expect(wrapper.find('.report-fallback').text()).toContain('Complete result.')
    expect(wrapper.text()).toContain('已生成')
  })

  it('shows a synchronization state instead of zero final artifacts after completion', () => {
    const wrapper = mount(GenericArtifactPanel, {
      props: {
        status: 'completed',
        finalReport: null,
        finalArtifacts: [],
        stepOutputs: [{ stepId: 'analysis', name: '分析', status: 'completed', output: { result: 'done' } }]
      }
    })

    expect(wrapper.text()).toContain('正在整理最终成果')
    expect(wrapper.text()).not.toContain('最终交付物 0 项')
  })
})
