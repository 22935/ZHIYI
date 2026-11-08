import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import RuntimeObservationNotice from './RuntimeObservationNotice.vue'

describe('RuntimeObservationNotice', () => {
  it('distinguishes missing observations from empty records and clears after recovery', async () => {
    const observation = { runId: 'run_1', unavailableSources: ['trace', 'context'] } as RuntimeObservation
    const wrapper = mount(RuntimeObservationNotice, { props: { runId: 'run_1', observation } })
    expect(wrapper.get('[role="status"]').text()).toContain('执行追踪、上下文数据暂时无法读取')
    expect(wrapper.text()).toContain('当前空白不代表没有记录')
    await wrapper.setProps({ observation: { ...observation, unavailableSources: [] } })
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })

  it('does not show a previous run failure after selection changes', () => {
    const wrapper = mount(RuntimeObservationNotice, { props: {
      runId: 'run_2', observation: { runId: 'run_1', unavailableSources: ['run'] } as RuntimeObservation
    } })
    expect(wrapper.find('[role="status"]').exists()).toBe(false)
  })
})
