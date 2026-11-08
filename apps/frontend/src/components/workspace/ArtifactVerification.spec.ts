import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ArtifactVerification from './ArtifactVerification.vue'

describe('ArtifactVerification', () => {
  it('shows partial verification and its checks and gaps without claiming tests passed', () => {
    const wrapper = mount(ArtifactVerification, { props: { verification: {
      status: 'partial', checks: [{ criterion: '恢复测试', result: '未执行', evidence: '仅有设计' }], unresolvedGaps: ['缺少实测']
    } } })
    expect(wrapper.text()).toContain('产物验证：部分通过')
    expect(wrapper.text()).toContain('不等同于独立测试结果')
    expect(wrapper.text()).toContain('结果：未执行')
    expect(wrapper.text()).toContain('依据：仅有设计')
    expect(wrapper.text()).toContain('缺少实测')
    expect(wrapper.findAll('details')).toHaveLength(2)
  })

  it('does not infer successful verification when results are missing or unknown', async () => {
    const wrapper = mount(ArtifactVerification)
    expect(wrapper.text()).toContain('未提供验证结果')
    await wrapper.setProps({ verification: { status: 'new_status', checks: [], unresolvedGaps: [] } })
    expect(wrapper.text()).toContain('状态未识别（new_status）')
  })
})
