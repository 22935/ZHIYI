import { describe, expect, it, vi } from 'vitest'
import { conversationWorkbenchTarget, workbenchConversationTarget } from './navigation'
import type { ChatWorkflowBinding } from '@/stores/chat'

const binding = (overrides: Partial<ChatWorkflowBinding> = {}): ChatWorkflowBinding => ({
  conversationId: 'ctx', conversationAliases: ['draft:old', 'legacy'], missionId: 'mission', runId: 'run',
  source: 'chat', status: 'running', createdAt: '1', acgTaskId: 'run', clientRequestId: 'request', ...overrides
})
const readRun = () => vi.fn(async (runId: string) => ({ runId, missionId: 'mission', status: 'running' }))
const readConversation = () => vi.fn(async (contextId: string) => ({ contextId, workspaceMode: 'chat' } as any))

describe('Verified Conversation / Workbench navigation', () => {
  it('rejects competing canonical owners even without shared aliases', async () => {
    expect(await conversationWorkbenchTarget({ ctx: [binding()], other: [binding({ conversationId: 'other', conversationAliases: [] })] },
      'ctx', 'run', readRun())).toBeNull()
  })
  it('rejects a binding invalidated during backend verification', async () => {
    const item = binding()
    const read = vi.fn(async () => { item.invalidAt = 'now'; return { runId: 'run', missionId: 'mission', status: 'running' } })
    expect(await conversationWorkbenchTarget({ ctx: [item] }, 'ctx', 'run', read)).toBeNull()
  })
  it('resolves aliases to the original Mission/Run without changing the index', async () => {
    const index = { ctx: [binding()] }; const original = JSON.stringify(index)
    for (const id of ['ctx', 'draft:old', 'legacy']) {
      expect(await conversationWorkbenchTarget(index, id, undefined, readRun())).toEqual({
        path: '/agentos/missions/mission/workspace', query: { runId: 'run' }
      })
    }
    expect(JSON.stringify(index)).toBe(original)
  })
  it('retains an explicitly selected historical Run instead of selecting a newer active one', async () => {
    const index = { ctx: [binding({ runId: 'old', status: 'completed' }), binding({ runId: 'new', createdAt: '2' })] }
    expect((await conversationWorkbenchTarget(index, 'ctx', 'old', readRun()))?.query.runId).toBe('old')
    expect((await conversationWorkbenchTarget(index, 'ctx', undefined, readRun()))?.query.runId).toBe('new')
    expect(await conversationWorkbenchTarget(index, 'ctx', 'unbound', readRun())).toBeNull()
  })
  it('does not choose between conflicting canonical owners of the same Alias', async () => {
    const index = { ctx: [binding()], other: [binding({ conversationId: 'other' })] }
    expect(await conversationWorkbenchTarget(index, 'draft:old', 'run', readRun())).toBeNull()
  })
  it.each(['absent', 'invalid', 'mission', 'run', 'denied'])('fails closed for %s Chat associations', async reason => {
    const read = readRun()
    if (reason === 'mission') read.mockResolvedValue({ runId: 'run', missionId: 'other', status: 'running' })
    if (reason === 'run') read.mockResolvedValue({ runId: 'other', missionId: 'mission', status: 'running' })
    if (reason === 'denied') read.mockRejectedValue(new Error('403'))
    const index = reason === 'absent' ? {} : { ctx: [binding(reason === 'invalid' ? { invalidAt: 'now' } : {})] }
    expect(await conversationWorkbenchTarget(index, 'ctx', 'run', read)).toBeNull()
  })
  it('returns the canonical context and original mode, never an Alias or Mission ID', async () => {
    expect(await workbenchConversationTarget({ index: { ctx: [binding()] }, missionId: 'mission', runId: 'run',
      draftId: 'draft:other', currentContextId: null, readRun: readRun(), readConversation: readConversation() })).toEqual({
      path: '/chat', query: { contextId: 'ctx', missionId: 'mission', runId: 'run', workspace: 'chat' }
    })
  })
  it.each(['absent', 'invalid', 'mission', 'run', 'denied', 'wrong-context', 'ambiguous'])('fails closed for %s Workbench associations', async reason => {
    const read = readRun(), conversation = readConversation()
    if (reason === 'mission') read.mockResolvedValue({ runId: 'run', missionId: 'other', status: 'running' })
    if (reason === 'run') read.mockResolvedValue({ runId: 'other', missionId: 'mission', status: 'running' })
    if (reason === 'denied') conversation.mockRejectedValue(new Error('403'))
    if (reason === 'wrong-context') conversation.mockResolvedValue({ contextId: 'another' } as any)
    const index = reason === 'absent' ? {} : { ctx: [binding(reason === 'invalid' ? { invalidAt: 'now' } : {})] }
    if (reason === 'ambiguous') index.ctx.push(binding({ conversationId: 'other' }))
    expect(await workbenchConversationTarget({ index, missionId: 'mission', runId: 'run', draftId: null,
      currentContextId: null, readRun: read, readConversation: conversation })).toBeNull()
  })
  it('returns a Draft only when it is still the same local blank Conversation', async () => {
    const options = { index: { 'draft:D': [binding({ conversationId: 'draft:D', source: 'agent' })] }, missionId: 'mission',
      runId: 'run', draftId: 'draft:D', currentContextId: null, readRun: readRun(), readConversation: readConversation() }
    expect((await workbenchConversationTarget(options))?.query).toEqual({ missionId: 'mission', runId: 'run', workspace: 'agent' })
    expect(options.readConversation).not.toHaveBeenCalled()
    expect(await workbenchConversationTarget({ ...options, draftId: 'draft:other' })).toBeNull()
    expect(await workbenchConversationTarget({ ...options, currentContextId: 'unrelated' })).toBeNull()
  })
  it.each(['run-query', 'conversation-query', 'replacement', 'owner', 'alias'])('rejects reverse navigation changed during %s', async stage => {
    const item = binding(); const index = { ctx: [item] }
    const mutate = () => {
      if (stage === 'replacement') index.ctx = [binding({ source: 'agent' })]
      else if (stage === 'owner') index.ctx.push(binding({ conversationId: 'other', missionId: 'other' }))
      else if (stage === 'alias') index.ctx.push(binding({ conversationId: 'other', runId: 'other' }))
      else item.invalidAt = 'revoked'
    }
    const run = vi.fn(async () => { if (stage === 'run-query') mutate(); return { runId: 'run', missionId: 'mission', status: 'running' } })
    const conversation = vi.fn(async () => { if (stage !== 'run-query') mutate(); return { contextId: 'ctx', workspaceMode: 'chat' } as any })
    expect(await workbenchConversationTarget({ index, missionId: 'mission', runId: 'run', draftId: null,
      currentContextId: 'ctx', readRun: run, readConversation: conversation })).toBeNull()
  })

})
