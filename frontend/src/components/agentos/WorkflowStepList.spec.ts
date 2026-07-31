import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowStepList from './WorkflowStepList.vue'

describe('WorkflowStepList conditional status compatibility', () => {
  it('renders skipped-by-condition and falls back for an unknown status', () => {
    const wrapper = mount(WorkflowStepList, {
      props: {
        steps: [
          { stepId: 'skipped', name: 'Skipped', agentName: 'none', status: 'skipped_by_condition' },
          { stepId: 'future', name: 'Future', agentName: 'none', status: 'future_status' as never }
        ]
      },
      global: { stubs: { 'el-icon': true } }
    })

    expect(wrapper.text()).toContain('条件跳过')
    expect(wrapper.text()).toContain('future_status')
    expect(wrapper.find('.step-card.skipped_by_condition').exists()).toBe(true)
  })
})
