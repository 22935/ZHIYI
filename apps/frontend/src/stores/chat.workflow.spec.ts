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
      startWorkflowAsync: vi.fn(),
      reconcileMissionLaunch: vi.fn()
    }
  }
})

const acceptedResponse = {
  runId: 'run_chat_1',
  missionId: 'mission_chat_1',
  workflowId: 'legal_case_analysis_v1',
  domain: 'legal',
  status: 'pending' as const,
  steps: []
}

describe('chat workflow binding', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    setActivePinia(createPinia())
    vi.resetAllMocks()
    vi.mocked(workflowApi.startWorkflowAsync).mockResolvedValue(acceptedResponse)
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'NOT_FOUND' })
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
      missionId: 'mission_chat_1',
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

  it.each(['before-request', 'pending-response'])('keeps a late launch binding with its original Conversation without writing new messages (%s)', async phase => {
    let deliver!: (value: any) => void
    vi.mocked(workflowApi.startWorkflowAsync).mockReturnValue(new Promise(ok => { deliver = ok }))
    const store = useChatStore()
    const pending = store.startAgentRun('original goal', { conversationId: 'original', clientRequestId: 'original-operation' })
    if (phase === 'pending-response') await vi.waitFor(() => expect(workflowApi.startWorkflowAsync).toHaveBeenCalledTimes(1))
    store.clearMessages(); store.contextId = 'new-context'
    store.addMessage({ id: 'new', role: 'user', content: 'new Conversation' })
    deliver(acceptedResponse)
    const result = await pending
    expect(result?.binding.conversationId).toBe('original')
    expect(store.getLatestWorkflowBinding('original')?.runId).toBe('run_chat_1')
    expect(store.contextId).toBe('new-context')
    expect(store.messages.map(item => item.content)).toEqual(['new Conversation'])
    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledTimes(1)
    expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0].clientRequestId).toBe('original-operation')
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
    expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[1][0])
      .toEqual(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0])
  })

  it('freezes Conversation context and execution settings across response loss and Store recreation', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(new Error('lost')).mockResolvedValueOnce(acceptedResponse)
    const store = useChatStore()
    store.contextId = 'server-chat-context'
    store.currentRoleId = 'role'
    const options = { conversationId: 'local-conversation', clientRequestId: 'operation', execution: { thinkingMode: 'deep' as const } }
    await expect(store.upgradeToWorkflow('正式目标', options)).rejects.toThrow('lost')
    const first = vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0]
    expect(first).toMatchObject({ semantics: { objective: '正式目标' }, input: {
      conversationId: 'local-conversation', chatContextId: 'server-chat-context', chatRoleId: 'role', thinkingMode: 'deep'
    } })
    setActivePinia(createPinia())
    const reloaded = useChatStore()
    reloaded.contextId = 'changed-context'
    await expect(reloaded.upgradeToWorkflow('正式目标', { ...options, execution: { thinkingMode: 'disabled' } })).rejects.toMatchObject({ code: 'BUSY' })
    const result = await reloaded.upgradeToWorkflow('正式目标', options)
    expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[1][0]).toEqual(first)
    expect(result?.launch).toEqual({ missionId: acceptedResponse.missionId, runId: acceptedResponse.runId,
      run: acceptedResponse, clientRequestId: 'operation' })
    expect(result?.binding.conversationId).toBe('local-conversation')
  })

  it('coalesces the same operation but refuses a different Chat/Agent intent in the same Conversation', async () => {
    let resolve: (value: any) => void
    vi.mocked(workflowApi.startWorkflowAsync).mockImplementation(() => new Promise(r => { resolve = r }))
    const store = useChatStore()
    const options = { conversationId: 'conversation', clientRequestId: 'operation' }
    const chat = store.upgradeToWorkflow('目标', options)
    const repeat = store.upgradeToWorkflow('目标', options)
    await expect(store.startAgentRun('目标', { ...options, clientRequestId: 'other-operation' })).rejects.toMatchObject({ code: 'BUSY' })
    await vi.waitFor(() => expect(workflowApi.startWorkflowAsync).toHaveBeenCalledTimes(1))
    resolve!(acceptedResponse)
    expect(await chat).toEqual(await repeat)
    expect(store.messages.filter(m => m.role === 'user')).toHaveLength(1)
    expect(store.messages.filter(m => m.workflowRunId)).toHaveLength(1)
    expect(store.workflowBindings.conversation).toHaveLength(1)
  })

  it('preserves 409 and blocks new identity until the original operation is reconciled', async () => {
    const error = { response: { status: 409 } }
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(error).mockResolvedValueOnce(acceptedResponse)
    const store = useChatStore()
    await expect(store.startAgentRun('目标', { conversationId: 'conversation', clientRequestId: 'old' })).rejects.toBe(error)
    expect(store.getLatestWorkflowBinding('conversation')).toBeUndefined()
    await expect(store.startAgentRun('目标', { conversationId: 'conversation', clientRequestId: 'new' })).rejects.toMatchObject({ code: 'BUSY' })
    vi.mocked(workflowApi.reconcileMissionLaunch).mockResolvedValue({ status: 'CREATED', missionId: acceptedResponse.missionId, runId: acceptedResponse.runId, run: acceptedResponse })
    await store.startAgentRun('目标', { conversationId: 'conversation', clientRequestId: 'old' })
    expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls.map(call => call[0].clientRequestId)).toEqual(['old'])
    expect(workflowApi.startWorkflow).not.toHaveBeenCalled()
  })
  it('refuses policy changes under an unconfirmed Conversation operation, including omitted versus empty scope', async () => {
    vi.mocked(workflowApi.startWorkflowAsync).mockRejectedValueOnce(new Error('lost'))
    const store = useChatStore()
    const options = {
      conversationId: 'conversation', clientRequestId: 'operation',
      domain: 'research', intent: 'analysis', reviewMode: 'human_in_loop'
    }
    await expect(store.upgradeToWorkflow('goal', options)).rejects.toThrow('lost')
    for (const changed of [{ domain: 'general' }, { reviewMode: 'auto' }, { workflowId: '' }, { enabledPluginIds: [] }, { enabledPluginIds: null }]) {
      await expect(store.upgradeToWorkflow('goal', { ...options, ...changed })).rejects.toMatchObject({ code: 'BUSY' })
    }
    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledTimes(1)
    const result = await store.resumeMissionLaunch('conversation')
    expect(result?.launch.clientRequestId).toBe('operation')
    expect(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[1][0]).toEqual(vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0])
  })
})
