import { describe, expect, it } from 'vitest'
import { IdleChoreographer, type IdleContext } from './idleBehavior'

const NOW = new Date(2026, 10, 6, 14, 0, 0).getTime()
const context = (overrides: Partial<IdleContext> = {}): IdleContext => ({
  now: NOW,
  lastInteractionAt: NOW - 120_000,
  state: 'idle',
  mood: 'content',
  quiet: false,
  hidden: false,
  ...overrides
})

describe('idle choreographer', () => {
  it('stays silent for quiet mode, hidden tabs and non-idle states', () => {
    const choreographer = new IdleChoreographer(120_000, 45_000, 900_000, () => 0)
    expect(choreographer.observe(context({ quiet: true })).line).toBeNull()
    expect(choreographer.observe(context({ hidden: true })).line).toBeNull()
    expect(choreographer.observe(context({ state: 'thinking' })).line).toBeNull()
    expect(choreographer.observe(context({ state: 'error' })).line).toBeNull()
  })

  it('waits for real idle time before speaking', () => {
    const choreographer = new IdleChoreographer(120_000, 45_000, 900_000, () => 0)
    expect(choreographer.observe(context({ lastInteractionAt: NOW - 10_000 })).line).toBeNull()
    expect(choreographer.observe(context()).line).not.toBeNull()
  })

  it('throttles repeated lines and honors the injected random gate', () => {
    const always = new IdleChoreographer(120_000, 45_000, 900_000, () => 0)
    expect(always.observe(context()).line).not.toBeNull()
    expect(always.observe(context({ now: NOW + 1000 })).line).toBeNull()
    expect(always.observe(context({ now: NOW + 121_000 })).line).not.toBeNull()

    const never = new IdleChoreographer(120_000, 45_000, 900_000, () => 0.99)
    expect(never.observe(context()).line).toBeNull()
  })

  it('puts the companion to sleep after a long absence and keeps it asleep', () => {
    const choreographer = new IdleChoreographer(120_000, 45_000, 900_000, () => 0)
    const longAway = context({ lastInteractionAt: NOW - 20 * 60_000 })
    const first = choreographer.observe(longAway)
    expect(first.sleep).toBe(true)
    expect(first.line).toContain('z')
    const second = choreographer.observe({ ...longAway, state: 'sleeping' })
    expect(second.sleep).toBe(true)
    expect(second.line).toBeNull()
  })

  it('reset clears the throttle so a fresh session can speak again', () => {
    const choreographer = new IdleChoreographer(120_000, 45_000, 900_000, () => 0)
    expect(choreographer.observe(context()).line).not.toBeNull()
    choreographer.reset()
    expect(choreographer.observe(context({ now: NOW + 1000 })).line).not.toBeNull()
  })
})
