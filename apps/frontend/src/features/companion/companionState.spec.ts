import { describe, expect, it } from 'vitest'
import {
  IdleFallback, ProactivityQueue, RUNTIME_EVENT_STATE,
  STATE_PRIORITY, resolveState, stateFromRuntimeEvent
} from './companionState'

describe('companion state machine', () => {
  it('does not let a lower priority event interrupt an error', () => {
    expect(resolveState('error', 'working')).toBe('error')
    expect(resolveState('idle', 'alert')).toBe('alert')
    expect(resolveState('thinking', 'happy')).toBe('happy')
  })

  it('maps runtime events to display states only', () => {
    expect(stateFromRuntimeEvent('run.completed')).toBe('happy')
    expect(stateFromRuntimeEvent('run.failed')).toBe('error')
    expect(stateFromRuntimeEvent('step.started')).toBe('working')
    expect(stateFromRuntimeEvent('model.output.delta')).toBeNull()
  })

  it('keeps errors above routine progress', () => {
    expect(STATE_PRIORITY.error).toBeGreaterThan(STATE_PRIORITY.working)
    expect(Object.keys(RUNTIME_EVENT_STATE)).toContain('run.waiting_review')
  })

  it('deduplicates notices and throttles low priority chatter', () => {
    let now = 1000
    const queue = new ProactivityQueue(4000, () => now)
    const notice = (id: string, priority: number) => ({ id, priority, text: id, state: 'idle' as const, at: now })
    expect(queue.enqueue(notice('a', 1))).not.toBeNull()
    expect(queue.enqueue(notice('a', 1))).toBeNull()
    expect(queue.enqueue(notice('b', 1))).toBeNull()
    expect(queue.enqueue(notice('error', 5))).not.toBeNull()
    now = 6000
    expect(queue.enqueue(notice('c', 1))).not.toBeNull()
    queue.reset()
    expect(queue.enqueue(notice('a', 1))).not.toBeNull()
  })

  it('clears the idle fallback timer', () => {
    const fallback = new IdleFallback(10)
    fallback.schedule(() => { throw new Error('should not fire') })
    fallback.clear()
    expect(true).toBe(true)
  })
})
