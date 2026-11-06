import { describe, expect, it } from 'vitest'
import { resolveMissionLaunchPolicy } from './policy'
import { createNativeWorkbenchDraft } from '@/features/acg/workbench'
import { conversationLaunchCommand, workbenchLaunchCommand } from './command'

describe('MissionLaunchPolicyResolver', () => {
  it.each([
    [{}, { domain: 'general', intent: 'general', reviewMode: 'auto', enabledPluginIds: undefined }],
    [{ domain: 'general', intent: 'general', reviewMode: 'auto' }, { domain: 'general', intent: 'general', reviewMode: 'auto' }],
    [{ workflowId: '', enabledPluginIds: [] }, { workflowId: '', enabledPluginIds: [] }],
    [{ enabledPluginIds: null }, { enabledPluginIds: null }],
    [{ enabledPluginIds: ['plugin'], reviewMode: 'human_in_loop' }, { enabledPluginIds: ['plugin'], reviewMode: 'human_in_loop' }]
  ])('preserves omitted/default/empty/null semantics: %j', (explicit, expected) => {
    expect(resolveMissionLaunchPolicy({ entry: 'conversation', explicit })).toMatchObject(expected)
  })
  it('inherits only omitted values, never overwriting explicit empty scope', () => {
    expect(resolveMissionLaunchPolicy({ entry: 'conversation', explicit: { enabledPluginIds: [], workflowId: '' },
      inherited: { domain: 'historical', enabledPluginIds: ['old'], workflowId: 'old', reviewMode: 'auto' } }))
      .toMatchObject({ domain: 'historical', enabledPluginIds: [], workflowId: '', reviewMode: 'auto' })
  })
  it('owns the existing general/general/auto Conversation View preset', () => {
    expect(resolveMissionLaunchPolicy({ entry: 'conversation', explicit: {}, profile: 'conversation-workspace' }))
      .toMatchObject({ domain: 'general', intent: 'general', reviewMode: 'auto' })
  })
  it.each(['workbench', 'legacy-acg'] as const)('retains Draft and Extension policy for %s', entry => {
    const draft = { ...createNativeWorkbenchDraft(), enabledPluginIds: ['authorized'] }
    expect(resolveMissionLaunchPolicy({ entry, draft, extensions: [{ pluginId: 'plugin', displayName: 'plugin',
      buildStartRequest: () => ({ domain: 'industry', intent: 'design', workflowId: 'workflow', reviewMode: 'human_in_loop',
        enabledPluginIds: ['escape'], clientRequestId: 'escape', input: { customFact: true } }) }] }))
      .toMatchObject({ domain: 'industry', intent: 'design', workflowId: 'workflow', reviewMode: 'human_in_loop',
        enabledPluginIds: ['authorized'], input: { customFact: true } })
  })
  it('normalizes both entry commands with the same explicit core semantics and execution settings', () => {
    const conversation = conversationLaunchCommand({ goal: 'goal', conversationId: 'c', chatContextId: 'ctx', chatRoleId: null,
      messages: [], source: 'chat', domain: 'general', intent: 'general', reviewMode: 'auto', enabledPluginIds: [], execution: { thinkingMode: 'deep', webSearchEnabled: false } })
    const workbench = workbenchLaunchCommand({ ...createNativeWorkbenchDraft(), taskGoal: 'goal', thinkingMode: 'deep', webSearchEnabled: false }, [])
    for (const key of ['semantics', 'domain', 'intent', 'reviewMode', 'enabledPluginIds'] as const) expect(conversation.request[key]).toEqual(workbench.request[key])
    expect(conversation.request.input).toMatchObject({ thinkingMode: 'deep', webSearchEnabled: false })
    expect(workbench.request.input).toMatchObject({ thinkingMode: 'deep', webSearchEnabled: false })
  })
})
