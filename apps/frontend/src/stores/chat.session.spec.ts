import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { chatApi } from '@/services/api/chat'
import { conversationApi } from '@/services/api/conversation'
import { useChatStore } from './chat'
import { useWorkflowRunsStore } from './workflowRuns'
import { createMissionLaunchAttempt } from '@/features/mission/launchAttempt'
import { conversationLaunchCommand } from '@/features/mission/command'
import { workflowApi } from '@/services/api/workflow'
import { agentosRequest } from '@/services/api/agentos/client'
import request from '@/utils/request'

vi.mock('@/services/api/chat', () => ({ chatApi: { getHistory: vi.fn(), sendMessage: vi.fn() } }))
vi.mock('@/services/api/conversation', () => ({ conversationApi: { getConversation: vi.fn() } }))
const deferred = <T>() => {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}
describe('Conversation history continuity', () => {
  beforeEach(() => { localStorage.clear(); localStorage.setItem('userId', 'local-owner'); sessionStorage.clear(); setActivePinia(createPinia()); vi.resetAllMocks() })
  afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
  it('restores the context key and its role rather than the database UUID', async () => {
    const agentPost = vi.spyOn(agentosRequest, 'post'); const chatPost = vi.spyOn(request, 'post')
    const uuid = vi.spyOn(crypto, 'randomUUID')
    vi.mocked(chatApi.getHistory).mockResolvedValue([{ id: 'm', role: 'user', content: 'original' }])
    vi.mocked(conversationApi.getConversation).mockResolvedValue({ id: 'database-uuid', contextId: 'ctx-A', roleId: 'role-A' } as any)
    const store = useChatStore()
    store.setRole('previous-role')
    await store.loadHistory('ctx-A')
    expect(store.contextId).toBe('ctx-A')
    expect(store.currentRoleId).toBe('role-A')
    expect(store.messages[0].content).toBe('original')
    expect(agentPost).not.toHaveBeenCalled(); expect(chatPost).not.toHaveBeenCalled(); expect(uuid).not.toHaveBeenCalled()
  })
  it('restores persisted reasoning content for history messages', async () => {
    vi.mocked(chatApi.getHistory).mockResolvedValue([{
      id: 'm-reasoning',
      role: 'assistant',
      content: 'answer',
      metadata: {
        reasoningContent: 'persisted thought',
        reasoningTruncated: true,
        thinkingEnabled: true
      }
    } as any])
    vi.mocked(conversationApi.getConversation).mockResolvedValue({ contextId: 'ctx-reasoning', roleId: 'role' } as any)
    const store = useChatStore()
    await store.loadHistory('ctx-reasoning')
    expect(store.messages[0].reasoningContent).toBe('persisted thought')
    expect(store.messages[0].reasoningTruncated).toBe(true)
    expect(store.messages[0].thinkingState).toBe('complete')
  })
  it('ignores both late metadata and messages from A after switching to B', async () => {
    const a = deferred<any[]>()
    const metaA = deferred<any>()
    vi.mocked(chatApi.getHistory).mockImplementation(async id => id === 'A' ? a.promise : [{ content: 'B' }])
    vi.mocked(conversationApi.getConversation).mockImplementation(async id => id === 'A' ? metaA.promise : { contextId: 'B', roleId: 'role-B' } as any)
    const store = useChatStore()
    const old = store.loadHistory('A')
    await store.loadHistory('B')
    a.resolve([{ content: 'A' }]); metaA.resolve({ contextId: 'A', roleId: 'role-A' })
    await old
    expect(store.contextId).toBe('B')
    expect(store.currentRoleId).toBe('role-B')
    expect(store.messages[0].content).toBe('B')
    expect(store.isLoadingConversation).toBe(false)
  })
  it('does not let an obsolete failure clear B loading or messages', async () => {
    const a = deferred<any[]>(); const b = deferred<any[]>()
    vi.mocked(chatApi.getHistory).mockImplementation(id => id === 'A' ? a.promise : b.promise)
    vi.mocked(conversationApi.getConversation).mockImplementation(async id => ({ contextId: id, roleId: id } as any))
    const store = useChatStore()
    const old = store.loadHistory('A'); const current = store.setContextId('B')
    a.reject(new Error('obsolete failure')); await old
    expect(store.isLoadingConversation).toBe(true)
    expect(store.contextId).toBe('B')
    b.resolve([{ content: 'B' }]); await current
    expect(store.messages[0].content).toBe('B')
    expect(chatApi.getHistory).toHaveBeenCalledTimes(2)
  })
  it('does not treat a missing context or draft as history, and keeps the new chat role', async () => {
    const store = useChatStore(); store.setRole('chosen')
    await store.loadHistory(''); await store.loadHistory('draft:unknown'); await store.setContextId(null)
    expect(chatApi.getHistory).not.toHaveBeenCalled()
    expect(conversationApi.getConversation).not.toHaveBeenCalled()
    expect(store.currentRoleId).toBe('chosen')
  })
  it('does not apply metadata from a different context and blocks continuation with an unknown role', async () => {
    vi.mocked(chatApi.getHistory).mockResolvedValue([])
    vi.mocked(conversationApi.getConversation).mockResolvedValue({ contextId: 'wrong', roleId: 'wrong-role' } as any)
    const store = useChatStore(); store.setRole('old-role')
    await store.loadHistory('ctx')
    expect(store.currentRoleId).toBeNull()
    await expect(store.sendMessage('continue')).rejects.toThrow('元数据')
    expect(chatApi.sendMessage).not.toHaveBeenCalled()
  })
  it('continues a legacy Agent context with its original transport mode for both send paths', async () => {
    vi.mocked(chatApi.getHistory).mockResolvedValue([])
    vi.mocked(conversationApi.getConversation).mockResolvedValue({ id: 'uuid', contextId: 'ctx-agent', roleId: 'role', workspaceMode: 'agent' } as any)
    vi.mocked(chatApi.sendMessage).mockResolvedValue({ contextId: 'ctx-agent', text: 'reply' } as any)
    const store = useChatStore(); await store.loadHistory('ctx-agent')
    await store.sendMessage('file', '/file', undefined, 'chat')
    expect(chatApi.sendMessage).toHaveBeenCalledWith(expect.objectContaining({ contextId: 'ctx-agent', workspaceMode: 'agent', roleId: 'role' }))
    const fetchMock = vi.fn().mockResolvedValue(new Response('data:[DONE]\n\n'))
    vi.stubGlobal('fetch', fetchMock)
    await store.sendMessageStream('continue', 'default', undefined, 'chat')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ context_id: 'ctx-agent', role_id: 'role', workspace_mode: 'agent' })
  })
  it('invalidates a pending history response when a new draft starts', async () => {
    const history = deferred<any[]>(); vi.mocked(chatApi.getHistory).mockReturnValue(history.promise)
    vi.mocked(conversationApi.getConversation).mockResolvedValue({ contextId: 'old', roleId: 'old' } as any)
    const store = useChatStore(); const loading = store.loadHistory('old'); store.clearMessages(); store.setRole('chosen')
    history.resolve([{ content: 'old' }]); await loading
    expect(store.contextId).toBeNull(); expect(store.messages).toEqual([]); expect(store.currentRoleId).toBe('chosen')
    expect(store.isLoadingConversation).toBe(false)
  })
  it('migrates only local association indexes without messages, references, new requests, or snapshot mutation', () => {
    const store = useChatStore(); const runs = useWorkflowRunsStore()
    const item = (runId: string, missionId = 'M', conversationId = 'draft:D') => ({
      conversationId, missionId, runId, acgTaskId: runId, source: 'chat' as const,
      clientRequestId: `original-${runId}`, createdAt: runId, status: 'running'
    })
    store.addWorkflowBinding(item('1')); store.addWorkflowBinding(item('2')); store.addWorkflowBinding(item('3', 'other'))
    store.addWorkflowBinding(item('1', 'M', 'ctx'))
    store.addMessage({ id: 'message', role: 'assistant', content: 'created', workflowRunId: '1' })
    const attempt = createMissionLaunchAttempt({ slot: 'conversation:draft:D' })
    attempt.begin(conversationLaunchCommand({ goal: 'frozen goal', messages: [], conversationId: 'draft:D', source: 'chat', chatContextId: null, chatRoleId: 'frozen-role' }), 'original-operation')
    const before = JSON.stringify(sessionStorage); const snapshot = attempt.pending()
    const uuid = vi.spyOn(crypto, 'randomUUID')
    const create = vi.spyOn(workflowApi, 'startWorkflowAsync'); const material = vi.spyOn(workflowApi, 'createMaterial')
    store.contextId = 'ctx'
    store.migrateDraftBindings('draft:unknown', 'ctx')
    expect(store.workflowBindings['draft:D']).toHaveLength(3)
    store.migrateDraftBindings('draft:D', 'wrong-context')
    expect(store.workflowBindings['draft:D']).toHaveLength(3)
    store.migrateDraftBindings('draft:D', 'ctx'); store.migrateDraftBindings('draft:D', 'ctx')
    expect(store.workflowBindings.ctx).toHaveLength(3)
    expect(store.getLatestWorkflowBinding('draft:D')?.runId).toBe('3')
    expect(store.messages).toHaveLength(1)
    expect(Object.keys(runs.references)).toHaveLength(3)
    expect(runs.getByConversation('ctx')).toHaveLength(3)
    expect(runs.getByConversation('draft:D')).toHaveLength(3)
    expect(JSON.stringify(sessionStorage)).toBe(before); expect(attempt.pending()).toEqual(snapshot)
    expect(uuid).not.toHaveBeenCalled(); expect(create).not.toHaveBeenCalled(); expect(material).not.toHaveBeenCalled()
    setActivePinia(createPinia())
    expect(useChatStore().getLatestWorkflowBinding('draft:D')?.runId).toBe('3')
    expect(useWorkflowRunsStore().getByConversation('draft:D')).toHaveLength(3)
  })

  it('keeps a new draft conversation separate from a migrated conversation alias', () => {
    const store = useChatStore()
    const binding = (conversationId: string, missionId: string, runId: string, conversationAliases?: string[]) => ({
      conversationId, conversationAliases, missionId, runId, acgTaskId: runId, source: 'chat' as const,
      clientRequestId: `request-${runId}`, createdAt: runId, status: 'running'
    })
    store.addWorkflowBinding(binding('draft:old', 'mission-old', 'run-old'))
    store.contextId = 'ctx-old'
    store.migrateDraftBindings('draft:old', 'ctx-old')
    store.addWorkflowBinding(binding('draft:new', 'mission-new', 'run-new'))

    expect(store.getActiveWorkflowBinding('ctx-old')?.runId).toBe('run-old')
    expect(store.getActiveWorkflowBinding('draft:old')?.runId).toBe('run-old')
    expect(store.getActiveWorkflowBinding('draft:new')?.runId).toBe('run-new')
    expect(store.getLatestWorkflowBinding('draft:new')?.conversationAliases).toBeUndefined()
    expect(store.getLatestWorkflowBinding('ctx-old')?.conversationAliases).toContain('draft:old')
  })
})
