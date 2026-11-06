import { describe, expect, it } from 'vitest'
import {
  buildWorkbenchStartRequest,
  createNativeWorkbenchDraft,
  restoreWorkbenchDraft,
} from './workbench'

describe('ACG workbench request builder', () => {
  it('defaults to an explicit Native-only scope', () => {
    const draft = createNativeWorkbenchDraft()
    const request = buildWorkbenchStartRequest(draft, [], 'request-native')

    expect(request).toMatchObject({
      domain: 'general', intent: 'general', workflowId: undefined,
      enabledPluginIds: [], reviewMode: 'auto', clientRequestId: 'request-native'
    })
    expect(request.input.source).toBe('acg')
    expect(request.input.webSearchEnabled).toBe(true)
    expect(request.input.capabilityProfile).toBe('auto')
    expect(request.input).not.toHaveProperty('contractText')
    expect(draft.title).toBe('')
    expect(draft.taskGoal).toBe('')
    expect(draft.expectedArtifacts).toEqual([])
  })

  it('forwards controlled stochastic planning without changing plugin scope', () => {
    const draft = createNativeWorkbenchDraft()
    draft.planningDiversity = 'exploratory'
    draft.planningSeed = 284731

    const request = buildWorkbenchStartRequest(draft, [], 'request-random')

    expect(request.input.planningDiversity).toBe('exploratory')
    expect(request.input.planningSeed).toBe(284731)
    expect(request.enabledPluginIds).toEqual([])
  })

  it('forwards the complete migrated planning strategy to the native planner', () => {
    const draft = createNativeWorkbenchDraft()
    draft.planningMode = 'template_preferred'
    draft.planningDiversity = 'exploratory'
    draft.planningSeed = 42
    draft.thinkingMode = 'deep'
    draft.webSearchEnabled = false

    const request = buildWorkbenchStartRequest(draft, [], 'request-planning')

    expect(request.input).toMatchObject({
      planningMode: 'template_preferred',
      usePlanner: true,
      planningDiversity: 'exploratory',
      planningSeed: 42,
      thinkingMode: 'deep',
      webSearchEnabled: false
    })
  })

  it('keeps GLM reasoning_effort explicit in the ACG Run input', () => {
    const draft = createNativeWorkbenchDraft()
    draft.thinkingMode = 'deep'
    draft.reasoningEffort = 'high'

    const request = buildWorkbenchStartRequest(draft, [], 'request-glm-thinking')

    expect(request.input).toMatchObject({
      thinkingMode: 'deep',
      reasoningEffort: 'high'
    })
  })

  it('restores GLM reasoning_effort without converting it to a disabled mode', () => {
    const draft = createNativeWorkbenchDraft()
    restoreWorkbenchDraft(draft, {
      runId: 'run-glm-history',
      title: 'GLM 历史任务',
      input: { reasoningEffort: 'max', thinkingMode: 'disabled' }
    }, [])

    expect(draft.reasoningEffort).toBe('max')
    expect(draft.thinkingMode).toBe('deep')
  })

  it('forwards the user-controlled network choice', () => {
    const draft = createNativeWorkbenchDraft()
    draft.webSearchEnabled = false

    const request = buildWorkbenchStartRequest(draft, [], 'request-local-only')

    expect(request.input.webSearchEnabled).toBe(false)
  })

  it('restores the editable native workbench fields from a historical Run', () => {
    const draft = createNativeWorkbenchDraft()
    restoreWorkbenchDraft(draft, {
      runId: 'run_history',
      title: '历史港口调度方案',
      reviewMode: 'human_in_loop',
      enabledPluginIds: [],
      input: {
        taskGoal: '恢复原任务目标', materialText: '恢复原任务材料',
        constraints: ['控制预算', '两周交付'], expectedArtifacts: ['实施方案'],
        planningMode: 'template_preferred', planningDiversity: 'balanced', planningSeed: 42,
        webSearchEnabled: false, thinkingMode: 'deep'
      }
    }, [])

    expect(draft).toMatchObject({
      title: '历史港口调度方案', taskGoal: '恢复原任务目标', materialText: '恢复原任务材料',
      constraints: ['控制预算', '两周交付'], expectedArtifacts: ['实施方案'],
      planningMode: 'template_preferred', planningDiversity: 'balanced', planningSeed: 42,
      webSearchEnabled: false, thinkingMode: 'deep', reviewMode: 'human_in_loop'
    })
  })
})
