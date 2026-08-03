import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { workflowApi } from '@/services/api/workflow'
import { useChatStore } from './chat'

vi.mock('@/services/api/workflow', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/api/workflow')>()
  return {
    ...actual,
    workflowApi: {
      ...actual.workflowApi,
      startWorkflow: vi.fn(),
      startWorkflowAsync: vi.fn()
    }
  }
})

const acceptedResponse = {
  accepted: true,
  acgTaskId: 'run_chat_1',
  task: { taskId: 'task_chat_1', status: 'pending' },
  run: { runId: 'run_chat_1', workflowId: 'legal_case_analysis_v1', status: 'pending' }
}

describe('chat workflow binding', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
    vi.mocked(workflowApi.startWorkflowAsync).mockResolvedValue(acceptedResponse)
  })

  it('starts asynchronously and persists the conversation/message/run binding', async () => {
    const store = useChatStore()
    const result = await store.upgradeToWorkflow('审查这份合同', {
      domain: 'legal',
      intent: 'case_analysis',
      conversationId: 'conversation_1',
      clientRequestId: 'request_1'
    })

    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledWith(expect.objectContaining({
      clientRequestId: 'request_1',
      input: expect.objectContaining({ source: 'chat', caseText: '审查这份合同' })
    }))
    expect(workflowApi.startWorkflow).not.toHaveBeenCalled()
    expect(result?.binding).toEqual(expect.objectContaining({
      conversationId: 'conversation_1',
      messageId: expect.any(String),
      taskId: 'task_chat_1',
      acgTaskId: 'run_chat_1',
      runId: 'run_chat_1',
      workflowId: 'legal_case_analysis_v1',
      source: 'chat',
      clientRequestId: 'request_1'
    }))
    expect(store.messages[store.messages.length - 1]?.content).toBe('已创建 ACG 运行任务')
    expect(JSON.parse(localStorage.getItem('chat.workflow_bindings.v1') || '{}').conversation_1).toHaveLength(1)
  })

  it('starts Agent runs as a lightweight Agent projection over ACG', async () => {
    const store = useChatStore()

    const result = await store.startAgentRun('制定跨部门发布计划', {
      conversationId: 'conversation_agent_1',
      clientRequestId: 'request_agent_1',
      enabledPluginIds: ['programmer']
    })

    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Agent ACG：制定跨部门发布计划',
      enabledPluginIds: ['programmer'],
      input: expect.objectContaining({
        source: 'agent',
        userIntent: '制定跨部门发布计划',
        taskGoal: '制定跨部门发布计划'
      })
    }))
    expect(result?.binding).toEqual(expect.objectContaining({
      acgTaskId: 'run_chat_1',
      runId: 'run_chat_1',
      source: 'agent'
    }))
  })

  it('keeps workflow submission independent while Chat is streaming', async () => {
    const store = useChatStore()
    store.loading = true
    store.isStreaming = true

    await expect(store.upgradeToWorkflow('并行启动 ACG', {
      conversationId: 'conversation_1',
      clientRequestId: 'request_2'
    })).resolves.toBeDefined()

    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledOnce()
    expect(store.isStreaming).toBe(true)
  })

  it('updates terminal status without deleting historical bindings or chat content', async () => {
    const store = useChatStore()
    await store.upgradeToWorkflow('执行任务', {
      conversationId: 'conversation_1',
      clientRequestId: 'request_3'
    })
    const messageCount = store.messages.length

    store.updateWorkflowBindingStatus('conversation_1', 'run_chat_1', 'failed')

    expect(store.getActiveWorkflowBinding('conversation_1')).toBeUndefined()
    expect(store.getLatestWorkflowBinding('conversation_1')?.status).toBe('failed')
    expect(store.messages).toHaveLength(messageCount)
  })

  it('does not create a binding when asynchronous start fails', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValue({ response: { status: 503 } })
    const store = useChatStore()

    await expect(store.upgradeToWorkflow('失败任务', {
      conversationId: 'conversation_1',
      clientRequestId: 'request_4'
    })).rejects.toEqual({ response: { status: 503 } })
    expect(store.getLatestWorkflowBinding('conversation_1')).toBeUndefined()
  })

  it('reuses the triggering user message for an idempotent retry', async () => {
    vi.mocked(workflowApi.startWorkflowAsync)
      .mockRejectedValueOnce({ response: { status: 503 } })
      .mockResolvedValueOnce(acceptedResponse)
    const store = useChatStore()
    const options = { conversationId: 'conversation_1', clientRequestId: 'request_retry' }

    await expect(store.upgradeToWorkflow('重试任务', options)).rejects.toBeDefined()
    await store.upgradeToWorkflow('重试任务', options)

    expect(store.messages.filter(message => message.role === 'user')).toHaveLength(1)
  })
})
