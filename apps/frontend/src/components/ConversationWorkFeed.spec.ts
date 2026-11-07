import { shallowMount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ConversationWorkFeed from './ConversationWorkFeed.vue'
import { chatApi } from '@/services/api/chat'

const stubs = { 'el-icon': true }

const mountFeed = (items: any[]) => shallowMount(ConversationWorkFeed, {
  props: { items }
})

describe('ConversationWorkFeed（对话信息栏的命令与执行）', () => {
  it('shows the empty hint when the conversation has no work items', () => {
    const wrapper = mountFeed([])
    expect(wrapper.find('.work-feed__empty').exists()).toBe(true)
    expect(wrapper.find('.terminal-work').exists()).toBe(false)
  })

  it('renders terminal work with bounded command output', () => {
    const wrapper = mountFeed([{
      stage: 'tool:terminal:call_1',
      status: 'completed',
      description: '终端命令执行完成',
      terminal: {
        command: 'python -c "print(1)"',
        cwd: '/app/workspace',
        exitCode: 0,
        stdout: '1\n',
        stderr: '',
        timedOut: false,
        truncated: false
      }
    }])

    expect(wrapper.find('.terminal-work').exists()).toBe(true)
    expect(wrapper.find('.terminal-work__command').text()).toContain('python -c')
    expect(wrapper.find('.terminal-work__output').text()).toContain('1')
  })

  it('renders workspace file activity without exposing host paths', () => {
    const wrapper = mountFeed([{
      stage: 'tool:patch_file:call_1',
      status: 'completed',
      description: 'Edited file',
      activity: {
        kind: 'file_patch',
        capabilityId: 'fs.patch',
        relativePath: 'src/hello.txt',
        summary: 'Edited file',
        addedLines: 1,
        removedLines: 1
      }
    }])

    expect(wrapper.find('.file-work').exists()).toBe(true)
    expect(wrapper.find('.file-work__path').text()).toBe('src/hello.txt')
    expect(wrapper.find('.file-work').text()).toContain('+1 / -1')
    expect(wrapper.text()).not.toContain('C:\\Users\\LZX')
  })

  it('renders a failed file activity with its stable error code', () => {
    const wrapper = mountFeed([{
      stage: 'tool:write_file:call_2',
      status: 'failed',
      description: '写入失败',
      activity: {
        kind: 'file_write',
        relativePath: 'src/hello.txt',
        errorCode: 'PATH_OUTSIDE_WORKSPACE'
      }
    }])

    expect(wrapper.find('.file-work__error').text()).toContain('PATH_OUTSIDE_WORKSPACE')
  })

  it('renders a safe inline approval card without host authority fields', () => {
    const wrapper = mountFeed([{
      stage: 'tool:write_file:call_approval',
      status: 'approval_required',
      description: 'Write file: hello.txt',
      approval: {
        approvalId: 'approval_test',
        toolCallId: 'call_approval',
        invocationId: 'call_approval',
        toolName: 'write_file',
        capabilityId: 'fs.write',
        relativePath: 'hello.txt',
        operationSummary: 'Write file: hello.txt',
        createdAt: '2026-08-03T12:00:00Z',
        status: 'pending',
        sessionId: 'chat_session'
      }
    }])

    expect(wrapper.find('.approval-work').exists()).toBe(true)
    expect(wrapper.findAll('.approval-work__button')).toHaveLength(3)
    expect(wrapper.find('.approval-work').text()).toContain('fs.write')
    expect(wrapper.find('.approval-work').text()).toContain('hello.txt')
    expect(wrapper.text()).not.toContain('C:\\Users\\LZX')
    expect(wrapper.text()).not.toContain('grant_')
    expect(wrapper.text()).not.toContain('credential')
  })

  it('sends the original approval correlation when allowing once', async () => {
    const resolve = vi.spyOn(chatApi, 'resolveApproval').mockResolvedValue({
      approvalId: 'approval_test',
      status: 'resolved',
      decision: 'allow_once'
    })
    const wrapper = mountFeed([{
      stage: 'tool:write_file:call_approval',
      status: 'approval_required',
      description: 'Write file: hello.txt',
      approval: {
        approvalId: 'approval_test',
        toolCallId: 'call_approval',
        invocationId: 'call_approval',
        toolName: 'write_file',
        capabilityId: 'fs.write',
        relativePath: 'hello.txt',
        operationSummary: 'Write file: hello.txt',
        createdAt: '2026-08-03T12:00:00Z',
        status: 'pending',
        sessionId: 'chat_session'
      }
    }])

    await wrapper.find('.approval-work__button.is-primary').trigger('click')
    expect(resolve).toHaveBeenCalledWith('approval_test', {
      decision: 'allow_once',
      sessionId: 'chat_session',
      invocationId: 'call_approval',
      capabilityId: 'fs.write',
      relativePath: 'hello.txt'
    })
    await wrapper.findAll('.approval-work__button')[1].trigger('click')
    await wrapper.findAll('.approval-work__button')[2].trigger('click')
    expect(resolve.mock.calls.map(call => call[1].decision)).toEqual([
      'allow_once',
      'allow_session',
      'deny'
    ])
    resolve.mockRestore()
  })

  it('does not render approval for read/list activity', () => {
    const wrapper = mountFeed([
      {
        stage: 'tool:read_file:call_read',
        status: 'completed',
        description: 'Read file',
        activity: { kind: 'file_read', capabilityId: 'fs.read', relativePath: 'hello.txt' }
      },
      {
        stage: 'tool:list_files:call_list',
        status: 'completed',
        description: 'Listed directory',
        activity: { kind: 'file_list', capabilityId: 'fs.list', relativePath: '.' }
      }
    ])

    expect(wrapper.find('.approval-work').exists()).toBe(false)
  })

  it('renders shell approval as allow-once or deny with the host risk notice', () => {
    const wrapper = mountFeed([{
      stage: 'tool:run_command:call-shell',
      status: 'approval_required',
      description: 'Run command',
      approval: {
        approvalId: 'approval-shell', toolCallId: 'call-shell', invocationId: 'call-shell',
        toolName: 'run_command', capabilityId: 'shell.exec', relativePath: '.',
        operationSummary: 'Run command: echo hello', operation: 'Run command',
        command: 'echo hello', cwd: '.',
        riskNotice: '当前 Windows 用户权限', createdAt: '2026-08-03T12:00:00Z',
        status: 'pending', sessionId: 'chat_session'
      }
    }])

    expect(wrapper.findAll('.approval-work__button')).toHaveLength(2)
    expect(wrapper.find('.approval-work').text()).toContain('shell.exec')
    expect(wrapper.find('.approval-work').text()).toContain('当前 Windows 用户权限')
  })

  it('keeps approval and resulting file activity associated', () => {
    const wrapper = mountFeed([
      {
        stage: 'tool:write_file:call-approved',
        status: 'completed',
        description: 'Created file',
        activity: { kind: 'file_write', relativePath: 'approved.txt' },
        approval: {
          approvalId: 'approval-approved', toolCallId: 'call-approved', invocationId: 'call-approved',
          toolName: 'write_file', capabilityId: 'fs.write', relativePath: 'approved.txt',
          operationSummary: 'Write file: approved.txt', createdAt: '2026-08-03T12:00:00Z',
          status: 'approved', sessionId: 'chat_session'
        }
      },
      {
        stage: 'tool:patch_file:call-denied',
        status: 'failed',
        description: 'Patch denied',
        activity: { kind: 'file_patch', relativePath: 'denied.txt', errorCode: 'PERMISSION_DENIED' },
        approval: {
          approvalId: 'approval-denied', toolCallId: 'call-denied', invocationId: 'call-denied',
          toolName: 'patch_file', capabilityId: 'fs.patch', relativePath: 'denied.txt',
          operationSummary: 'Patch file: denied.txt', createdAt: '2026-08-03T12:00:00Z',
          status: 'denied', sessionId: 'chat_session'
        }
      }
    ])

    expect(wrapper.findAll('.approval-work__card')).toHaveLength(2)
    expect(wrapper.find('.file-work').text()).toContain('PERMISSION_DENIED')
    expect(wrapper.find('.approval-work').text()).toContain('已允许')
    expect(wrapper.find('.approval-work').text()).toContain('已拒绝')
  })
})
