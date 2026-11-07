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

  it('shows the live execution phase below partial assistant content', () => {
    const wrapper = shallowMount(MessageBubble, {
      props: {
        message: {
          id: 'assistant-continuing',
          role: 'assistant',
          content: '我先读取当前文件，然后进行优化升级。',
          createdAt: new Date('2026-08-03T12:00:00Z'),
          thinkingState: 'complete',
          thinkingDurationMs: 10_000,
          streamActivity: 'waiting',
          streamPhase: '等待模型继续'
        }
      },
      global: { stubs: { 'el-icon': true, 'el-tooltip': { template: '<span><slot /></span>' }, 'el-progress': true, ImageViewer: true } }
    })

    const status = wrapper.find('.continuation-status')
    expect(status.exists()).toBe(true)
    expect(status.text()).toContain('执行脉络')
    expect(status.text()).toContain('等待模型继续')
    expect(wrapper.find('.thinking-status__phase').text()).toBe('已思考（用时 10 秒）')
    expect(status.element.compareDocumentPosition(wrapper.find('.message-actions').element) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('removes the continuation status after the stream completes', () => {
    const wrapper = shallowMount(MessageBubble, {
      props: {
        message: {
          id: 'assistant-complete',
          role: 'assistant',
          content: '任务已完成。',
          createdAt: new Date('2026-08-03T12:00:00Z'),
          streamActivity: 'complete',
          streamPhase: '已完成'
        }
      },
      global: { stubs: { 'el-icon': true, 'el-tooltip': { template: '<span><slot /></span>' }, 'el-progress': true, ImageViewer: true } }
    })

    expect(wrapper.find('.continuation-status').exists()).toBe(false)
  })

  it('keeps command and file work out of the conversation (renders in the info dock feed instead)', () => {
    const wrapper = shallowMount(MessageBubble, {
      props: {
        message: {
          id: 'assistant-work',
          role: 'assistant',
          content: '命令已执行，文件已更新。',
          createdAt: new Date('2026-08-03T12:00:00Z'),
          executionSummary: [
            {
              stage: 'tool:run_command:call-shell',
              status: 'approval_required',
              description: 'Run command',
              approval: {
                approvalId: 'approval-shell', toolCallId: 'call-shell', invocationId: 'call-shell',
                toolName: 'run_command', capabilityId: 'shell.exec', relativePath: '.',
                operationSummary: 'Run command: echo hello', operation: 'Run command',
                command: 'echo hello', cwd: '.', riskNotice: '当前 Windows 用户权限',
                createdAt: '2026-08-03T12:00:00Z', status: 'pending', sessionId: 'chat_session'
              }
            },
            {
              stage: 'tool:terminal:call_1',
              status: 'completed',
              description: '终端命令执行完成',
              terminal: {
                command: 'python -c "print(1)"', cwd: '/app/workspace', exitCode: 0,
                stdout: '1
', stderr: '', timedOut: false, truncated: false
              }
            },
            {
              stage: 'tool:patch_file:call_2',
              status: 'completed',
              description: 'Edited file',
              activity: { kind: 'file_patch', capabilityId: 'fs.patch', relativePath: 'src/hello.txt' }
            }
          ]
        }
      },
      global: { stubs: { 'el-icon': true, 'el-tooltip': { template: '<span><slot /></span>' }, 'el-progress': true, ImageViewer: true } }
    })

    expect(wrapper.find('.approval-work').exists()).toBe(false)
    expect(wrapper.find('.terminal-work').exists()).toBe(false)
    expect(wrapper.find('.file-work').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('需要确认命令执行')
    expect(wrapper.text()).not.toContain('退出码')
  })
})
