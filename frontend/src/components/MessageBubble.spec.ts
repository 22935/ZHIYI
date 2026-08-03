import { shallowMount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MessageBubble from './MessageBubble.vue'

const mountAssistant = (content: string) => shallowMount(MessageBubble, {
  props: {
    message: {
      id: 'assistant-table',
      role: 'assistant',
      content,
      createdAt: new Date('2026-08-03T12:00:00Z')
    }
  },
  global: {
    stubs: {
      'el-icon': true,
      'el-tooltip': { template: '<span><slot /></span>' },
      'el-progress': true,
      ImageViewer: true
    }
  }
})

describe('MessageBubble Markdown rendering', () => {
  it('renders Markdown tables in assistant replies', () => {
    const wrapper = mountAssistant([
      '| 风险编号 | 风险标题 | 修改建议 |',
      '| --- | --- | --- |',
      '| risk-001 | 付款节点倒挂 | 验收后付款 |'
    ].join('\n'))

    expect(wrapper.find('.markdown-table-wrap').exists()).toBe(true)
    expect(wrapper.findAll('th').map(cell => cell.text())).toEqual(['风险编号', '风险标题', '修改建议'])
    expect(wrapper.findAll('td').map(cell => cell.text())).toEqual(['risk-001', '付款节点倒挂', '验收后付款'])
  })

  it('keeps raw HTML escaped while rendering Markdown', () => {
    const wrapper = mountAssistant('<script>alert("x")</script> **安全内容**')

    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.find('strong').text()).toBe('安全内容')
    expect(wrapper.text()).toContain('<script>')
  })
})
