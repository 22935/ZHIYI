import { describe, expect, it } from 'vitest'
import {
  graphVersionChanged,
  mapEdgeVisualState,
  mapNodeVisualState,
  runtimeProjectionChanged
} from './runtimePresentation'

const progress = (graphVersion = 1, bindingSwitchCount = 0) => ({
  graphVersion, bindingSwitchCount, dynamicStepCount: 0,
  conditionalDecisionCount: 0, skippedByConditionCount: 0
}) as any

describe('runtime presentation helpers', () => {
  it('distinguishes graph refreshes from lightweight progress changes', () => {
    expect(graphVersionChanged(progress(2), progress(1))).toBe(true)
    expect(graphVersionChanged(progress(1), progress(1))).toBe(false)
    expect(runtimeProjectionChanged(progress(1, 1), progress(1, 0))).toBe(true)
    expect(runtimeProjectionChanged(progress(1, 0), progress(1, 0))).toBe(false)
  })

  it('maps all exposed edge activation states with a safe fallback', () => {
    expect(['active', 'inactive', 'terminated', 'superseded'].map(mapEdgeVisualState)).toEqual([
      'active', 'inactive', 'terminated', 'superseded'
    ])
    expect(mapEdgeVisualState('future_state')).toBe('active')
  })

  it('maps runtime-added, switched, retried and skipped node markers', () => {
    expect(mapNodeVisualState({
      stepId: 'risk', status: 'skipped_by_condition', agentName: 'agent', attempt: 2,
      retryCount: 1, createdGraphVersion: 2, bindingSwitchCount: 1
    })).toEqual({
      status: 'skipped_by_condition', runtimeAdded: true, bindingSwitched: true,
      conditionalSkipped: true, targetRetried: true
    })
  })
})
